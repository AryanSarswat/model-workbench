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
