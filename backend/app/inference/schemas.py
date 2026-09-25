from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


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


class ChatChunk(BaseModel):
    delta: str = ""
    done: bool = False
    error: str | None = None
    # Set only on the terminal (done=True) chunk; they describe the whole turn.
    usage: TokenUsage | None = None
    tools_called: list[str] = []
    retries: int = 0


class BackendCapabilities(BaseModel):
    structured_output_mode: Literal["grammar", "guided", "prompt_retry"]
    native_tool_calling: bool
