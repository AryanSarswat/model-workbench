from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ResponseMetricRecord(SQLModel, table=True):
    __tablename__ = "response_metrics"

    id: int | None = Field(default=None, primary_key=True)
    model_id: str
    backend: str  # "api" | "gguf" | "transformers"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_per_sec: float | None = None
    ttft_ms: float | None = None
    latency_ms: float
    # Always None: no pricing source is wired up yet.
    cost_usd: float | None = None
    ram_used_gb: float
    vram_used_gb: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
