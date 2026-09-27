from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class DownloadedModelBase(SQLModel):
    repo_id: str = Field(index=True)
    backend: str  # "gguf" | "transformers"
    quant: str | None = None  # GGUF filename when backend == "gguf", else None
    local_path: str
    size_bytes: int
    downloaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None


class DownloadedModelRecord(DownloadedModelBase, table=True):
    __tablename__ = "downloaded_models"

    id: int | None = Field(default=None, primary_key=True)


class DownloadedModel(DownloadedModelBase):
    """A record as `GET /models/downloaded` returns it."""

    id: int
    # What to send as a chat/eval request's model_id to run this record
    # (see app.inference.registry.local_model_ids).
    model_id: str
    # Why the installed llama.cpp can't load this GGUF; None when it can, and always
    # None for transformers snapshots.
    unsupported_reason: str | None = None
