from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlmodel import AutoString, Field, SQLModel

# Statuses of a job that hasn't finished yet (vs. "completed" / "failed").
ACTIVE_DOWNLOAD_STATUSES = ("pending", "downloading")


class DownloadJob(SQLModel, table=True):
    __tablename__ = "download_jobs"

    id: int | None = Field(default=None, primary_key=True)
    repo_id: str = Field(index=True)
    kind: Literal["gguf", "snapshot"] = Field(default="gguf", sa_type=AutoString)
    filename: str | None = None  # the requested GGUF file; None for snapshots
    current_file: str | None = None  # file currently downloading (snapshots only)
    status: Literal["pending", "downloading", "completed", "failed"] = Field(
        default="pending", sa_type=AutoString
    )
    percent: float = 0.0
    detail: str = "queued"
    error: str | None = None
    downloaded_model_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
