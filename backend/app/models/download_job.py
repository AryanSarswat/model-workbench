from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class DownloadJob(SQLModel, table=True):
    __tablename__ = "download_jobs"

    id: int | None = Field(default=None, primary_key=True)
    repo_id: str = Field(index=True)
    filename: str
    status: str = "pending"  # "pending" | "downloading" | "completed" | "failed"
    percent: float = 0.0
    detail: str = "queued"
    error: str | None = None
    downloaded_model_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
