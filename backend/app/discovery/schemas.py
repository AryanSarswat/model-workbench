from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DiscoveredModel(BaseModel):
    id: str
    author: str | None = None
    pipeline_tag: str | None = None
    downloads: int | None = None
    likes: int | None = None
    trending_score: float | None = None
    created_at: datetime | None = None
    gated: bool | str | None = None  # HF returns False, or a string reason like "auto"/"manual"
