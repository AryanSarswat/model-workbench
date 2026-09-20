from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class EvalResult(SQLModel, table=True):
    __tablename__ = "eval_results"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="eval_runs.id", ondelete="CASCADE", index=True)
    case_id: str  # the test case's own uuid -- not a DB FK, the dataset lives in JSON files
    category: str
    response: str
    structured_output_mode: str | None = None  # backend.capabilities().structured_output_mode
    native_tool_calling: bool = False
    retries: int = 0
    # Comma-joined tool names -- SQLite has no array column type and this repo has
    # no precedent for a JSON column, so a delimited string matches the existing
    # simplicity bar (same choice as assertions_detail below).
    tools_called: str = ""
    assertions_passed: int = 0
    assertions_total: int = 0
    assertions_detail: str = "[]"  # JSON-encoded list of {type, passed, detail}
    judge_score: float | None = None
    judge_rationale: str | None = None
    manual_verdict: str | None = None  # "pass" | "fail" | None until reviewed
    manual_notes: str | None = None
    response_metric_id: int | None = Field(default=None, foreign_key="response_metrics.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
