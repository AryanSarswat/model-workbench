from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class EvalRun(SQLModel, table=True):
    __tablename__ = "eval_runs"

    id: int | None = Field(default=None, primary_key=True)
    model_id: str
    backend: str
    category: str | None = None  # None runs every category
    judge_model_id: str | None = None
    status: str = "running"  # "running" | "completed"
    total_cases: int = 0
    completed_cases: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
