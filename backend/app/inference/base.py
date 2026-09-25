"""The common interface every inference backend implements; callers depend on this
shape, never on a specific backend.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage
from app.inference.structured_output import validate_output_schema
from app.tools import ToolSpec


class InferenceBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...

    def prevalidate_output_schema(self, schema: dict) -> None:
        """Reject a bad output_schema before StreamingResponse starts (a 400, not a
        mid-stream error). Backends whose generator-time setup can reject a
        dict-shaped schema run that same check here. Sync and model-free.
        """
        validate_output_schema(schema)

    async def stream_chat(
        self,
        model_id: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> AsyncIterator[ChatChunk]: ...

    async def aclose(self) -> None: ...
