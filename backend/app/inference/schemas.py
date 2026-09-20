from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class ChatChunk(BaseModel):
    delta: str = ""
    done: bool = False
    error: str | None = None
    # The next three fields are only ever populated on the terminal (done=True)
    # chunk -- they describe the whole turn, not one delta. tools_called and
    # retries feed the eval engine's tool_called / structured_output_first_try
    # assertions (see docs/architecture.md's eval engine section); usage feeds
    # response_metrics' tokens_per_sec.
    usage: TokenUsage | None = None
    tools_called: list[str] = []
    retries: int = 0


class BackendCapabilities(BaseModel):
    structured_output_mode: Literal["grammar", "guided", "prompt_retry"]
    native_tool_calling: bool
