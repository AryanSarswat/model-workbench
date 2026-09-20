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
from app.tools import ToolSpec, resolve_tool_names

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    model_id: str
    messages: list[ChatMessage]
    backend: str = "api"
    tools: list[str] | None = None
    output_schema: dict | None = None


async def _sse_events(
    backend: InferenceBackend,
    model_id: str,
    messages: list[ChatMessage],
    tools: list[ToolSpec] | None = None,
    output_schema: dict | None = None,
) -> AsyncIterator[str]:
    try:
        async for chunk in backend.stream_chat(
            model_id, messages, tools=tools, output_schema=output_schema
        ):
            yield f"data: {chunk.model_dump_json()}\n\n"
    finally:
        await backend.aclose()


@router.post("/stream")
def stream_chat(request: ChatRequest) -> StreamingResponse:
    # Invalid schemas are a 400 pre-stream -- before StreamingResponse starts,
    # so the error is a normal JSON error body (same bucket as unknown_tool).
    # The backend's own hook runs (not just the shared dict check): a
    # dict-shaped-but-invalid schema would otherwise raise inside the generator
    # mid-stream, after the 200 already started.
    backend = get_backend(request.backend, request.model_id, get_settings().hf_api_key)
    if request.output_schema is not None:
        backend.prevalidate_output_schema(request.output_schema)
    specs = [tool.spec for tool in resolve_tool_names(request.tools)]
    return StreamingResponse(
        _sse_events(
            backend,
            request.model_id,
            request.messages,
            tools=specs or None,
            output_schema=request.output_schema,
        ),
        media_type="text/event-stream",
    )
