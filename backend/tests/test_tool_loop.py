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

    assert result.text == '{"reply": "5"}'
    assert result.tools_called == ["calculator"]
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

    assert result.text == '{"reply": "done"}'
    assert result.tools_called == []
    assert any("Tool 'nope' is not available." in m.content for m in seen[-1])


def test_garbage_then_reply_retries():
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return "hmm, let me think about this"
        return '{"reply": "hi"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs()))

    assert result.text == '{"reply": "hi"}'
    assert result.tools_called == []
    assert any("That was not valid JSON." in m.content for m in seen[-1])


def test_always_tool_calls_stops_after_max_iterations():
    calls: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        calls.append(list(history))
        return '{"tool": "calculator", "arguments": {"expression": "1 + 1"}}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs(), max_iterations=3))

    assert len(calls) == 3
    assert result.text == '{"tool": "calculator", "arguments": {"expression": "1 + 1"}}'
    # Every one of the 3 turns is a valid tool call, and the loop executes each
    # one as it goes -- there's no special-casing of the final iteration. With
    # max_iterations=3 that's 3 calculator executions; the 3rd execution's
    # result is appended to history but never fed to another generate() call,
    # since the loop simply ends once max_iterations is reached.
    assert result.tools_called == ["calculator", "calculator", "calculator"]


def test_two_different_tools_called_in_sequence_are_both_recorded(tmp_path):
    page = tmp_path / "page.txt"
    page.write_text("hello from the page")
    specs = [get_tool("calculator").spec, get_tool("web_fetch").spec]
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}'
        if len(seen) == 2:
            return f'{{"tool": "web_fetch", "arguments": {{"url": "{page.as_uri()}"}}}}'
        return '{"reply": "done"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), specs))

    assert result.text == '{"reply": "done"}'
    assert result.tools_called == ["calculator", "web_fetch"]


def test_each_executed_call_keeps_its_arguments_and_the_result_the_model_saw(tmp_path):
    # The UI needs what each call was asked and what it returned -- including a
    # failing fetch, whose "Error: ..." text is all the model ever saw.
    missing = (tmp_path / "missing.txt").as_uri()
    specs = [get_tool("calculator").spec, get_tool("web_fetch").spec]
    turns = [
        '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
        f'{{"tool": "web_fetch", "arguments": {{"url": "{missing}"}}}}',
        '{"reply": "done"}',
    ]

    async def generate(history: list[ChatMessage]) -> str:
        return turns.pop(0)

    result = asyncio.run(run_tool_loop(generate, _messages(), specs))

    calc, fetch = result.tool_calls
    assert (calc.name, calc.arguments, calc.result) == (
        "calculator",
        {"expression": "2 + 3"},
        "5",
    )
    assert (fetch.name, fetch.arguments) == ("web_fetch", {"url": missing})
    assert fetch.result.startswith("Error: ")
    assert all(call.duration_ms >= 0 for call in result.tool_calls)
