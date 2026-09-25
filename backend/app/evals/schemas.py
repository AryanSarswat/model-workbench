"""Request/response shapes for the eval endpoints -- kept separate from the
SQLModel tables in app/models so API contracts can evolve independently of
storage.
"""

from __future__ import annotations

from pydantic import BaseModel


class EvalRunRequest(BaseModel):
    model_id: str
    backend: str = "api"
    category: str | None = None  # None runs every category
    judge_model_id: str | None = None


class ManualVerdictUpdate(BaseModel):
    manual_verdict: str | None = None
    manual_notes: str | None = None
