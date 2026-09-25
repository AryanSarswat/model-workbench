"""POST /chat/stream (SSE) and chat-session CRUD.

Sessions are a record, not context management: the client still resends the full
history every request, and `session_id` only files a copy of the turn. Every turn,
with or without a session and successful or not, gets a response_metrics row.
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
from app.metrics import TurnRecorder
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
    session: Session,
    backend: InferenceBackend,
    backend_name: str,
    model_id: str,
    messages: list[ChatMessage],
    tools: list[ToolSpec] | None = None,
    output_schema: dict | None = None,
    on_complete: Callable[[str], None] | None = None,
) -> AsyncIterator[str]:
    # Only a stream that runs to exhaustion with no error chunk files its reply: a
    # partial reply (error, exception, client disconnect) would read as the model's
    # answer later. The metric is recorded regardless -- failed latency is still data.
    recorder = TurnRecorder()
    finished = False
    try:
        async for chunk in backend.stream_chat(
            model_id, messages, tools=tools, output_schema=output_schema
        ):
            recorder.observe(chunk)
            yield f"data: {chunk.model_dump_json()}\n\n"
        finished = True
    finally:
        await backend.aclose()
        if on_complete is not None and finished and recorder.error is None:
            on_complete(recorder.text)
        session.add(recorder.build_metric(model_id, backend_name))
        session.commit()


@router.post("/stream")
def stream_chat(request: ChatRequest, session: SessionDep) -> StreamingResponse:
    # Validate with the backend's own hook before StreamingResponse starts, so a
    # bad schema is a 400 instead of a mid-stream failure after the 200.
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
            session,
            backend,
            request.backend,
            request.model_id,
            request.messages,
            tools=specs or None,
            output_schema=request.output_schema,
            on_complete=on_complete,
        ),
        media_type="text/event-stream",
    )


@router.post("/sessions", status_code=201)
def create_chat_session(session: SessionDep) -> ChatSession:
    chat_session = ChatSession()
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return chat_session


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
    # The client resends full history, so only the trailing user message is new.
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
