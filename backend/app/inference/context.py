"""Build the context report: what a turn's last generation was given, per message."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import cast

from app.inference.schemas import ChatMessage, ContextKind, ContextMessage, ContextReport
from app.inference.tool_loop import is_tool_result


def build_context_report(
    request: list[ChatMessage],
    count_tokens: Callable[[str], int] | None,
    window: int | None,
    sent: Sequence[ChatMessage | dict] | None = None,
) -> ContextReport:
    """`sent` is what the model was given (default: the request as-is); anything in it
    the caller didn't send is the workbench's or the model's own."""
    own = {(m.role, m.content) for m in request}
    messages = []
    for item in request if sent is None else sent:
        message = item.model_dump() if isinstance(item, ChatMessage) else item
        content = message.get("content") or ""
        if not content and message.get("tool_calls"):
            content = json.dumps(message["tool_calls"])
        messages.append(
            ContextMessage(
                kind=_kind(message["role"], content, own),
                content=content,
                tokens=count_tokens(content) if count_tokens is not None else None,
            )
        )
    return ContextReport(window=window, messages=messages)


def _kind(role: str, content: str, own: set[tuple[str, str]]) -> ContextKind:
    if (role, content) in own:
        return cast(ContextKind, role)  # a request role: system, user or assistant
    if role == "tool" or (role == "user" and is_tool_result(content)):
        return "tool"
    if role == "assistant":
        return "assistant"  # the model's own tool-call turns
    return "instructions"  # the tool protocol prompt and retry feedback
