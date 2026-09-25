"""Tool registry -- the single source of truth for available tools.

Each tool is a module in this package exposing TOOL_SPEC and an async run(args)
function. This module wraps those plain functions in Tool and offers lookup by
name, so chat/eval code can filter to a subset via tool_names without importing
tool modules directly. New tool = new file + one entry in _TOOL_MODULE_NAMES.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app.errors import WorkbenchError


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict


class Tool:
    """A tool spec plus its run function (runtime wrapper, not a module)."""

    def __init__(self, spec: ToolSpec, run_fn: Callable[[dict], Awaitable[str]]):
        self.spec = spec
        self._run_fn = run_fn

    async def run(self, args: dict) -> str:
        return await self._run_fn(args)


# Explicit module list -- no filesystem scanning, so stray files can never be
# imported as tools.
_TOOL_MODULE_NAMES = ("app.tools.calculator", "app.tools.web_fetch")

_registry: dict[str, Tool] = {}


def _load() -> None:
    _registry.clear()
    for module_name in _TOOL_MODULE_NAMES:
        module = importlib.import_module(module_name)
        _registry[module.TOOL_SPEC.name] = Tool(
            spec=module.TOOL_SPEC, run_fn=module.run
        )


_load()


def list_tools() -> list[Tool]:
    return list(_registry.values())


def get_tool(name: str) -> Tool:
    try:
        return _registry[name]
    except KeyError:
        raise WorkbenchError(400, "unknown_tool", f"Unknown tool: {name}") from None


def resolve_tool_names(names: list[str] | None) -> list[Tool]:
    if not names:
        return []
    return [get_tool(name) for name in names]


def reload_tools() -> None:
    """Re-import the modules in _TOOL_MODULE_NAMES so edits on disk take effect. A new
    tool module isn't picked up here -- it needs a _TOOL_MODULE_NAMES entry and a restart."""
    for module_name in _TOOL_MODULE_NAMES:
        module = sys.modules.get(module_name)
        if module is not None:
            importlib.reload(module)
    _load()
