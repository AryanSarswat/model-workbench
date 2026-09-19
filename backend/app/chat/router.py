"""POST /chat/stream -- SSE chat completion. Only the HF Inference API backend exists so
far; llama.cpp/transformers (local, requiring model-loading/lifecycle management) are
separate follow-ups.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.errors import WorkbenchError
from app.inference.hf_api_backend import HFInferenceAPIBackend
from app.inference.schemas import ChatMessage

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    model_id: str
    messages: list[ChatMessage]
    # Not a Literal["api"]: an invalid backend name needs to hit the check below and
    # produce our uniform {error: {...}} shape, not FastAPI's default 422 validation body.
    backend: str = "api"


async def _sse_events(
    model_id: str, messages: list[ChatMessage], api_key: str
) -> AsyncIterator[str]:
    backend = HFInferenceAPIBackend(api_key)
    try:
        async for chunk in backend.stream_chat(model_id, messages):
            yield f"data: {chunk.model_dump_json()}\n\n"
    finally:
        await backend.aclose()


@router.post("/stream")
def stream_chat(request: ChatRequest) -> StreamingResponse:
    if request.backend != "api":
        raise WorkbenchError(
            status_code=400,
            code="backend_not_supported",
            message=f"Backend '{request.backend}' is not yet supported.",
        )

    api_key = get_settings().hf_api_key
    if not api_key:
        raise WorkbenchError(
            status_code=400,
            code="missing_hf_api_key",
            message="HF_API_KEY is not configured -- set it in backend/.env.",
        )

    return StreamingResponse(
        _sse_events(request.model_id, request.messages, api_key),
        media_type="text/event-stream",
    )
