"""GET /tools (list tool specs) and POST /tools/reload (re-import tool modules
after one is edited on disk)."""

from __future__ import annotations

from fastapi import APIRouter

from app.tools import ToolSpec, list_tools, reload_tools

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tool_specs() -> list[ToolSpec]:
    return [tool.spec for tool in list_tools()]


@router.post("/reload")
def reload_tool_modules() -> dict[str, int]:
    reload_tools()
    return {"count": len(list_tools())}
