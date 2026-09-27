from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlmodel import AutoString, Field, SQLModel

from app.inference.schemas import StructuredOutputMode

ManualVerdict = Literal["pass", "fail"]


class EvalResult(SQLModel, table=True):
    __tablename__ = "eval_results"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="eval_runs.id", ondelete="CASCADE", index=True)
    case_id: str  # the test case's own uuid -- not a DB FK, the dataset lives in JSON files
    category: str  # snapshotted from the case so aggregation needs no JSON reads
    response: str
    error: str | None = None  # backend error or invalid case schema; assertions then fail
    # backend.capabilities().structured_output_mode
    structured_output_mode: StructuredOutputMode | None = Field(default=None, sa_type=AutoString)
    native_tool_calling: bool = False
    retries: int = 0
    tools_called: str = ""  # comma-joined tool names (tool names never contain commas)
    assertions_passed: int = 0
    assertions_total: int = 0
    assertions_detail: str = "[]"  # JSON-encoded list of {type, passed, detail}
    judge_score: float | None = None
    judge_rationale: str | None = None
    # None until reviewed
    manual_verdict: ManualVerdict | None = Field(default=None, sa_type=AutoString)
    manual_notes: str | None = None
    response_metric_id: int | None = Field(default=None, foreign_key="response_metrics.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
