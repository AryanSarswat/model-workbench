"""The common interface every inference backend implements, per docs/architecture.md's
inference engine design -- callers (the chat router, later the eval engine) depend on this
shape, never on a specific backend.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage


class InferenceBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...

    async def stream_chat(
        self, model_id: str, messages: list[ChatMessage]
    ) -> AsyncIterator[ChatChunk]: ...

    async def aclose(self) -> None: ...
