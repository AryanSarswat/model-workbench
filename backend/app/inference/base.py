"""The common interface every inference backend implements, per docs/architecture.md's
inference engine design -- callers (the chat router, later the eval engine) depend on this
shape, never on a specific backend.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, Protocol

from pydantic import BaseModel

from app.inference.schemas import ChatChunk, ChatMessage


class BackendCapabilities(BaseModel):
    structured_output_mode: Literal["grammar", "guided", "prompt_retry"]
    native_tool_calling: bool


class InferenceBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...

    def stream_chat(
        self, model_id: str, messages: list[ChatMessage]
    ) -> AsyncIterator[ChatChunk]: ...
