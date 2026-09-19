from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    tags: list[str] = []
    library_name: str | None = None  # e.g. "transformers", "llama.cpp", "mlx"


class GgufFile(BaseModel):
    filename: str
    size_bytes: int


class SnapshotFile(BaseModel):
    """One file of a transformers snapshot -- repo-relative path, which may include
    subdirectories. size_bytes is None when the Hub reports no size; progress totals
    treat it as 0 rather than refusing the download."""

    filename: str
    size_bytes: int | None = None


class ModelDetail(DiscoveredModel):
    gguf_files: list[GgufFile] = []
    parameter_count: int | None = None
    dtype: str | None = None  # dominant dtype from safetensors metadata, e.g. "BF16"


class FeasibilityOption(BaseModel):
    label: str  # a GGUF filename, or e.g. "transformers (BF16)"
    verdict: Literal["comfortable", "tight", "wont_fit"]
    estimated_memory_gb: float
    reason: str


class FeasibilityReport(BaseModel):
    available_memory_gb: float
    options: list[FeasibilityOption]
