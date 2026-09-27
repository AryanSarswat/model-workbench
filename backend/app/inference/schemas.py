from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int


def combine_usage(turns: list[TokenUsage]) -> TokenUsage | None:
    """Usage for a multi-turn tool/schema loop: completion_tokens sums across turns,
    prompt_tokens is the last turn's (it already includes every prior turn's history).
    None when no turn reported usage."""
    if not turns:
        return None
    return TokenUsage(
        prompt_tokens=turns[-1].prompt_tokens,
        completion_tokens=sum(t.completion_tokens for t in turns),
    )


class ToolCallRecord(BaseModel):
    """One executed tool call: what the model asked for and what it was sent back."""

    name: str
    arguments: dict
    # Exactly the text fed back to the model -- a failure is its "Error: ..." text.
    result: str
    duration_ms: float


class ToolCallStart(BaseModel):
    """A tool call that has begun executing; its ToolCallRecord follows when it ends."""

    name: str
    arguments: dict


class ChatChunk(BaseModel):
    delta: str = ""
    done: bool = False
    error: str | None = None
    # Live progress of a tool turn, one chunk each: calls run one at a time, so a
    # finished record always closes the most recent start.
    tool_call_started: ToolCallStart | None = None
    tool_call_finished: ToolCallRecord | None = None
    # Set only on the terminal (done=True) chunk; they describe the whole turn.
    usage: TokenUsage | None = None
    tools_called: list[str] = []
    tool_calls: list[ToolCallRecord] = []
    retries: int = 0


class BackendCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)  # BACKEND_CAPABILITIES entries are shared

    structured_output_mode: Literal["grammar", "guided", "prompt_retry"]
    native_tool_calling: bool


# The single source of truth for what each backend can do. Lives here, not on the
# backend classes, so GET /backends can report it without importing the optional
# torch/llama.cpp modules; each class's capabilities() returns its entry.
BACKEND_CAPABILITIES: dict[str, BackendCapabilities] = {
    # A remote provider offers no grammar/guided decoding control.
    "api": BackendCapabilities(structured_output_mode="prompt_retry", native_tool_calling=False),
    "gguf": BackendCapabilities(structured_output_mode="grammar", native_tool_calling=True),
    "transformers": BackendCapabilities(structured_output_mode="guided", native_tool_calling=False),
}


class BackendInfo(BackendCapabilities):
    """GET /backends entry: a backend's capabilities, plus whether it can run here."""

    available: bool
