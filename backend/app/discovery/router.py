from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.discovery.hf_client import list_discoverable_models
from app.discovery.schemas import DiscoveredModel

router = APIRouter(prefix="/models", tags=["discovery"])


@router.get("/discover")
def discover_models(
    sort: Literal["trending", "recent"] = "trending",
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DiscoveredModel]:
    return list_discoverable_models(sort=sort, limit=limit)
