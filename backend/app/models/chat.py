from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChatMessageRecord(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chat_sessions.id", ondelete="CASCADE", index=True)
    role: str  # "user" | "assistant" -- system prompts are request-scoped, not stored
    content: str
    sequence: int = Field(index=True)  # append order within the session; GET orders by this
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
