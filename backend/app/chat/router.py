"""POST /chat/stream -- SSE chat completion. Depends only on the InferenceBackend
interface, not a specific backend -- get_backend() is where a (`backend`, `model_id`)
pair gets resolved to a concrete implementation. "api" is remote; "gguf" runs a
downloaded GGUF file via llama.cpp; "transformers" runs a downloaded snapshot via
transformers (for models without a GGUF build).
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
    backend = get_backend(request.backend, request.model_id, get_settings().hf_api_key)
    return StreamingResponse(
        _sse_events(backend, request.model_id, request.messages),
        media_type="text/event-stream",
    )
