"""POST /chat/stream -- SSE chat completion. Depends only on the InferenceBackend
interface, not a specific backend -- get_backend() is where a (`backend`, `model_id`)
pair gets resolved to a concrete implementation. "api" is remote; "gguf" runs a
downloaded GGUF file via llama.cpp; "transformers" runs a downloaded snapshot via
transformers (for models without a GGUF build).

Session persistence is a record, not context management: the client still resends the
full message history every request (stateless inference), and `session_id` only asks
the server to file a copy of the turn away. The stored history is never injected into
the model context.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.errors import WorkbenchError
from app.inference.base import InferenceBackend
from app.inference.registry import get_backend
from app.inference.schemas import ChatMessage
from app.models import ChatMessageRecord, ChatSession
from app.tools import ToolSpec, resolve_tool_names

router = APIRouter(prefix="/chat", tags=["chat"])

SessionDep = Annotated[Session, Depends(get_session)]


class ChatRequest(BaseModel):
    model_id: str
    messages: list[ChatMessage]
    backend: str = "api"
    tools: list[str] | None = None
    output_schema: dict | None = None
    session_id: int | None = None  # persist this turn into an existing session


class ChatSessionDetail(BaseModel):
    id: int
    created_at: datetime
    messages: list[ChatMessageRecord]


async def _sse_events(
    backend: InferenceBackend,
    model_id: str,
    messages: list[ChatMessage],
    tools: list[ToolSpec] | None = None,
    output_schema: dict | None = None,
    on_complete: Callable[[str], None] | None = None,
) -> AsyncIterator[str]:
    # Persist-on-error decision: only a stream that runs to exhaustion with no error
    # chunk persists its reply. Mid-stream failures, backend exceptions, and client
    # disconnects (GeneratorExit) persist nothing -- a partial/error reply filed as the
    # turn's assistant message would read as the model's answer on re-read.
    parts: list[str] = []
    failed = False
    finished = False
    try:
        async for chunk in backend.stream_chat(
            model_id, messages, tools=tools, output_schema=output_schema
        ):
            if chunk.error is not None:
                failed = True
            else:
                parts.append(chunk.delta)
            yield f"data: {chunk.model_dump_json()}\n\n"
        finished = True
    finally:
        await backend.aclose()
        if on_complete is not None and finished and not failed:
            on_complete("".join(parts))


@router.post("/stream")
def stream_chat(request: ChatRequest, session: SessionDep) -> StreamingResponse:
    # Invalid schemas are a 400 pre-stream -- before StreamingResponse starts,
    # so the error is a normal JSON error body (same bucket as unknown_tool).
    # The backend's own hook runs (not just the shared dict check): a
    # dict-shaped-but-invalid schema would otherwise raise inside the generator
    # mid-stream, after the 200 already started.
    backend = get_backend(request.backend, request.model_id, get_settings().hf_api_key)
    if request.output_schema is not None:
        backend.prevalidate_output_schema(request.output_schema)
    specs = [tool.spec for tool in resolve_tool_names(request.tools)]
    on_complete = None
    if request.session_id is not None:
        if session.get(ChatSession, request.session_id) is None:
            raise WorkbenchError(
                status_code=404,
                code="chat_session_not_found",
                message=f"No chat session with id {request.session_id}.",
            )
        _store_user_turn(session, request.session_id, request.messages)
        session_id = request.session_id

        def on_complete(reply: str) -> None:
            _store_assistant_reply(session, session_id, reply)

    return StreamingResponse(
        _sse_events(
            backend,
            request.model_id,
            request.messages,
            tools=specs or None,
            output_schema=request.output_schema,
            on_complete=on_complete,
        ),
        media_type="text/event-stream",
    )


@router.get("/sessions")
def list_chat_sessions(session: SessionDep) -> list[ChatSession]:
    return list(
        session.exec(
            select(ChatSession).order_by(ChatSession.created_at.desc(), ChatSession.id.desc())
        ).all()
    )


@router.get("/sessions/{session_id}")
def get_chat_session(session_id: int, session: SessionDep) -> ChatSessionDetail:
    chat_session = session.get(ChatSession, session_id)
    if chat_session is None:
        raise WorkbenchError(
            status_code=404,
            code="chat_session_not_found",
            message=f"No chat session with id {session_id}.",
        )
    messages = list(
        session.exec(
            select(ChatMessageRecord)
            .where(ChatMessageRecord.session_id == session_id)
            .order_by(ChatMessageRecord.sequence)
        ).all()
    )
    return ChatSessionDetail(
        id=chat_session.id, created_at=chat_session.created_at, messages=messages
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_chat_session(session_id: int, session: SessionDep) -> None:
    chat_session = session.get(ChatSession, session_id)
    if chat_session is None:
        raise WorkbenchError(
            status_code=404,
            code="chat_session_not_found",
            message=f"No chat session with id {session_id}.",
        )
    # Messages are deleted explicitly: SQLite only enforces ON DELETE CASCADE with
    # PRAGMA foreign_keys=ON, which this app never sets, so the DDL-level cascade on
    # ChatMessageRecord.session_id is a backstop, not the mechanism.
    for message in session.exec(
        select(ChatMessageRecord).where(ChatMessageRecord.session_id == session_id)
    ).all():
        session.delete(message)
    session.delete(chat_session)
    session.commit()


def _store_user_turn(
    session: Session, session_id: int, messages: list[ChatMessage]
) -> None:
    # The client resends full history every request, so only the trailing user message
    # (the new turn) is filed -- storing every user-role message would duplicate the
    # already-recorded history on every turn.
    new_turn = next((m for m in reversed(messages) if m.role == "user"), None)
    if new_turn is None:
        return
    session.add(
        ChatMessageRecord(
            session_id=session_id,
            role="user",
            content=new_turn.content,
            sequence=_next_sequence(session, session_id),
        )
    )
    session.commit()


def _store_assistant_reply(session: Session, session_id: int, reply: str) -> None:
    session.add(
        ChatMessageRecord(
            session_id=session_id,
            role="assistant",
            content=reply,
            sequence=_next_sequence(session, session_id),
        )
    )
    session.commit()


def _next_sequence(session: Session, session_id: int) -> int:
    last = session.exec(
        select(ChatMessageRecord.sequence)
        .where(ChatMessageRecord.session_id == session_id)
        .order_by(ChatMessageRecord.sequence.desc())
    ).first()
    return (last or 0) + 1
