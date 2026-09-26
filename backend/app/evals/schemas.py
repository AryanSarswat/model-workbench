"""Request/response shapes for the eval endpoints -- kept separate from the
SQLModel tables in app/models so API contracts can evolve independently of
storage.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvalRunRequest(BaseModel):
    model_id: str
    backend: str = "api"
    category: str | None = None  # None runs every category
    judge_model_id: str | None = None


class ManualVerdictUpdate(BaseModel):
    manual_verdict: Literal["pass", "fail"] | None = None  # the report's pass rule reads these
    manual_notes: str | None = None


class EvalReportRow(BaseModel):
    """One (model_id, backend, category) cell of the model-comparison report --
    see app/evals/report.py for how it's built.
    """

    model_id: str
    backend: str
    category: str
    cases: int  # distinct case_ids counted
    passed: int
    pass_rate: float  # passed / cases, 0..1
    avg_tokens_per_sec: float | None  # mean of non-null response_metrics.tokens_per_sec
    avg_ttft_ms: float | None  # mean of non-null response_metrics.ttft_ms
    structured_output_reliability: float | None  # share of schema_valid assertions passed
    tool_calling_reliability: float | None  # share of tool_called assertions passed
    latest_run_id: int  # newest run contributing to this row
