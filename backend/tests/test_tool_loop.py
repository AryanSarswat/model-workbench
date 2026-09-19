"""Focused tests for the fallback agentic tool loop, with scripted fake backends."""

import asyncio

from app.inference.schemas import ChatMessage
from app.inference.tool_loop import run_tool_loop
from app.tools import ToolSpec, get_tool


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="What is 2 + 3?")]


def _specs() -> list[ToolSpec]:
    return [get_tool("calculator").spec]


def test_tool_call_then_reply_returns_final_text_and_records_result():
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}'
        return '{"reply": "5"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs()))

    assert result == '{"reply": "5"}'
    assert any(
        "Tool 'calculator' returned: 5" in m.content for m in seen[-1] if m.role == "user"
    )


def test_unknown_tool_name_appends_error_and_continues():
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return '{"tool": "nope", "arguments": {}}'
        return '{"reply": "done"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs()))

    assert result == '{"reply": "done"}'
    assert any("Tool 'nope' is not available." in m.content for m in seen[-1])


def test_garbage_then_reply_retries():
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return "hmm, let me think about this"
        return '{"reply": "hi"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs()))

    assert result == '{"reply": "hi"}'
    assert any("That was not valid JSON." in m.content for m in seen[-1])


def test_always_tool_calls_stops_after_max_iterations():
    calls: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        calls.append(list(history))
        return '{"tool": "calculator", "arguments": {"expression": "1 + 1"}}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs(), max_iterations=3))

    assert len(calls) == 3
    assert result == '{"tool": "calculator", "arguments": {"expression": "1 + 1"}}'
