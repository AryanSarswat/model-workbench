"""Request/response shapes for the eval endpoints -- kept separate from the
SQLModel tables in app/models so API contracts can evolve independently of
storage.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.evals.assertions import AssertionResult
from app.inference.schemas import BackendName, StructuredOutputMode
from app.models.eval_result import ManualVerdict


class EvalRunRequest(BaseModel):
    model_id: str
    backend: BackendName = "api"
    category: str | None = None  # None runs every category
    judge_model_id: str | None = None


class ManualVerdictUpdate(BaseModel):
    manual_verdict: ManualVerdict | None = None  # the report's pass rule reads these
    manual_notes: str | None = None


class EvalResultOut(BaseModel):
    """An EvalResult as the API returns it: the report's pass rule applied, and the
    storage-encoded columns (comma-joined tools, JSON-encoded assertions) decoded.
    """

    id: int
    run_id: int
    case_id: str
    category: str
    response: str
    error: str | None
    structured_output_mode: StructuredOutputMode | None
    native_tool_calling: bool
    retries: int
    tools_called: list[str]
    assertions_passed: int
    assertions_total: int
    assertions: list[AssertionResult]
    judge_score: float | None
    judge_rationale: str | None
    manual_verdict: ManualVerdict | None
    manual_notes: str | None
    response_metric_id: int | None
    created_at: datetime
    passed: bool  # app/evals/report.py result_passed -- the same rule the report counts


class EvalReportRow(BaseModel):
    """One (model_id, backend, category) cell of the model-comparison report --
    see app/evals/report.py for how it's built.
    """

    model_id: str
    backend: BackendName
    category: str
    cases: int  # distinct case_ids counted
    passed: int
    pass_rate: float  # passed / cases, 0..1
    avg_tokens_per_sec: float | None  # mean of non-null response_metrics.tokens_per_sec
    avg_ttft_ms: float | None  # mean of non-null response_metrics.ttft_ms
    structured_output_reliability: float | None  # share of schema_valid assertions passed
    tool_calling_reliability: float | None  # share of tool_called assertions passed
    latest_run_id: int  # newest run contributing to this row
