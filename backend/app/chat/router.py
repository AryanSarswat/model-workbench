"""POST /chat/stream -- SSE chat completion. Depends only on the InferenceBackend
interface, not a specific backend -- get_backend() is where a `backend` name gets resolved
to a concrete implementation. Only "api" exists today; llama.cpp/transformers (local,
requiring model-loading/lifecycle management) are separate follow-ups that plug in there.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.inference.base import InferenceBackend
from app.inference.registry import get_backend
from app.inference.schemas import ChatMessage

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    model_id: str
    messages: list[ChatMessage]
    backend: str = "api"


async def _sse_events(
    backend: InferenceBackend, model_id: str, messages: list[ChatMessage]
) -> AsyncIterator[str]:
    try:
        async for chunk in backend.stream_chat(model_id, messages):
            yield f"data: {chunk.model_dump_json()}\n\n"
    finally:
        await backend.aclose()


@router.post("/stream")
def stream_chat(request: ChatRequest) -> StreamingResponse:
    backend = get_backend(request.backend, get_settings().hf_api_key)
    return StreamingResponse(
        _sse_events(backend, request.model_id, request.messages),
        media_type="text/event-stream",
    )
