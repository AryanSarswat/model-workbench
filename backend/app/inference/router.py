"""GET /backends: each inference backend's capabilities and whether it can run here,
so the UI reads them instead of keeping its own copy."""

from __future__ import annotations

from fastapi import APIRouter

from app.inference.registry import is_available
from app.inference.schemas import BACKEND_CAPABILITIES, BackendInfo

router = APIRouter(prefix="/backends", tags=["backends"])


@router.get("")
def list_backends() -> dict[str, BackendInfo]:
    return {
        name: BackendInfo(**capabilities.model_dump(), available=is_available(name))
        for name, capabilities in BACKEND_CAPABILITIES.items()
    }
