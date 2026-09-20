"""The common interface every inference backend implements, per docs/architecture.md's
inference engine design -- callers (the chat router, later the eval engine) depend on this
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
        """Reject a bad output_schema pre-stream (before StreamingResponse starts).

        Default is the shared dict/serializable check only; backends whose
        generator-time setup can reject dict-shaped-but-invalid schemas (grammar
        compile, guide build) override this to run that same check eagerly, so
        the failure is a 400 instead of a mid-stream error. Sync and cheap: no
        model load.
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
