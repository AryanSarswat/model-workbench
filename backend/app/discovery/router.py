from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.discovery.feasibility import estimate_feasibility
from app.discovery.hf_client import get_model_detail, list_discoverable_models
from app.discovery.schemas import DiscoveredModel, FeasibilityReport, ModelDetail

router = APIRouter(prefix="/models", tags=["discovery"])


@router.get("/discover")
def discover_models(
    sort: Literal["trending", "recent"] = "trending",
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DiscoveredModel]:
    return list_discoverable_models(sort=sort, limit=limit)


# NOTE: route order matters. Both routes below use a {model_id:path} catch-all, which
# matches ANY string including one ending in "/feasibility" -- so the more specific
# "/feasibility" route must be registered first, or it would never be reached (see
# tests/test_feasibility.py's route-ordering regression test).
@router.get("/{model_id:path}/feasibility")
def model_feasibility(model_id: str, quant: str | None = None) -> FeasibilityReport:
    return estimate_feasibility(model_id, quant=quant)


@router.get("/{model_id:path}")
def model_detail(model_id: str) -> ModelDetail:
    return get_model_detail(model_id)
