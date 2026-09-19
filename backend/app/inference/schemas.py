from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatChunk(BaseModel):
    delta: str = ""
    done: bool = False
    error: str | None = None


class BackendCapabilities(BaseModel):
    structured_output_mode: Literal["grammar", "guided", "prompt_retry"]
    native_tool_calling: bool
