"""Focused tests for the fallback agentic tool loop, with scripted fake backends."""

import asyncio

import pytest

from app.errors import WorkbenchError
from app.inference.schemas import ChatChunk, ChatMessage, ToolCallStart
from app.inference.tool_loop import (
    LoopResult,
    ToolEvents,
    ToolTurn,
    run_tool_loop,
    stream_tool_turn,
)
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

    assert result.text == "5"
    assert result.tools_called == ["calculator"]
    assert any("Tool 'calculator' returned: 5" in m.content for m in seen[-1] if m.role == "user")


def test_unknown_tool_name_appends_error_and_continues():
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return '{"tool": "nope", "arguments": {}}'
        return '{"reply": "done"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs()))

    assert result.text == "done"
    assert result.tools_called == []
    assert any("Tool 'nope' is not available." in m.content for m in seen[-1])


def test_registered_tool_the_request_did_not_enable_is_not_run():
    # The request's tools are the allowlist: a model (or a prompt injection) naming
    # any other registered tool must get the unknown-tool feedback, not a run.
    seen: list[list[ChatMessage]] = []
    events: list[ChatChunk] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return '{"tool": "web_fetch", "arguments": {"url": "http://127.0.0.1:1/"}}'
        return '{"reply": "done"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs(), on_event=events.append))

    assert result.tools_called == []
    assert events == []
    assert any("Tool 'web_fetch' is not available." in m.content for m in seen[-1])


def test_garbage_then_reply_retries():
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return "hmm, let me think about this"
        return '{"reply": "hi"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs()))

    assert result.text == "hi"
    assert result.tools_called == []
    assert any("That was not valid JSON." in m.content for m in seen[-1])


def test_schema_conforming_turn_is_the_final_reply():
    # With an output_schema the tool instruction asks for a schema-shaped final
    # reply, so a conforming object ends the loop; a non-conforming one is retried.
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }
    seen: list[list[ChatMessage]] = []
    turns = [
        '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
        '{"answer": "five"}',
        'Here you go: {"answer": 5}',
    ]

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        return turns.pop(0)

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs(), output_schema=schema))

    assert result.text == '{"answer": 5}'
    assert result.tools_called == ["calculator"]
    assert len(seen) == 3
    # The retry asks for the schema-shaped final answer, not a {"reply": ...} one.
    (retry,) = [m.content for m in seen[-1] if m.role == "user" and "JSON Schema" in m.content]
    assert "conforming to the schema" in retry
    assert '"reply"' not in retry


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


def test_two_different_tools_called_in_sequence_are_both_recorded():
    specs = [get_tool("calculator").spec, get_tool("web_fetch").spec]
    seen: list[list[ChatMessage]] = []

    async def generate(history: list[ChatMessage]) -> str:
        seen.append(list(history))
        if len(seen) == 1:
            return '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}'
        if len(seen) == 2:
            return '{"tool": "web_fetch", "arguments": {"url": "gopher://example.com/"}}'
        return '{"reply": "done"}'

    result = asyncio.run(run_tool_loop(generate, _messages(), specs))

    assert result.text == "done"
    assert result.tools_called == ["calculator", "web_fetch"]


def test_each_executed_call_keeps_its_arguments_and_the_result_the_model_saw():
    # The UI needs what each call was asked and what it returned -- including a
    # failing fetch, whose "Error: ..." text is all the model ever saw.
    unfetchable = "gopher://example.com/"
    specs = [get_tool("calculator").spec, get_tool("web_fetch").spec]
    turns = [
        '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
        f'{{"tool": "web_fetch", "arguments": {{"url": "{unfetchable}"}}}}',
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
    assert (fetch.name, fetch.arguments) == ("web_fetch", {"url": unfetchable})
    assert fetch.result.startswith("Error: ")
    assert all(call.duration_ms >= 0 for call in result.tool_calls)


def test_on_event_reports_each_call_as_it_starts_and_then_its_record():
    # The Playground shows a running card from the start event and swaps in the
    # finished record, so the pair must bracket the call and match the loop's record.
    turns = [
        '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
        '{"reply": "5"}',
    ]
    events: list[ChatChunk] = []

    async def generate(history: list[ChatMessage]) -> str:
        return turns.pop(0)

    result = asyncio.run(run_tool_loop(generate, _messages(), _specs(), on_event=events.append))

    started, finished = events
    assert started.tool_call_started == ToolCallStart(
        name="calculator", arguments={"expression": "2 + 3"}
    )
    assert finished.tool_call_finished == result.tool_calls[0]


def test_tool_events_yields_a_chunk_while_the_loop_is_still_running():
    release = asyncio.Event()

    async def loop(emit) -> str:
        emit(ChatChunk(tool_call_started=ToolCallStart(name="calculator", arguments={})))
        await release.wait()
        return "final"

    async def scenario() -> None:
        events = ToolEvents()
        task = asyncio.create_task(loop(events.emit))
        stream = events.stream(task)
        first = await anext(stream)
        assert first.tool_call_started.name == "calculator"
        assert not task.done()
        release.set()
        assert [chunk async for chunk in stream] == []
        assert task.result() == "final"

    asyncio.run(scenario())


def _collect_turn(run, **kwargs) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        return [chunk async for chunk in stream_tool_turn(run, **kwargs)]

    return asyncio.run(_collect())


def test_stream_tool_turn_yields_events_then_reply_and_done():
    async def run(emit) -> ToolTurn:
        emit(ChatChunk(tool_call_started=ToolCallStart(name="calculator", arguments={})))
        return ToolTurn(LoopResult(text="5"), usage=None, retries=2)

    started, reply, done = _collect_turn(run)

    assert started.tool_call_started.name == "calculator"
    assert reply.delta == "5"
    assert (done.done, done.error, done.retries) == (True, None, 2)


def test_stream_tool_turn_ends_a_failure_in_an_error_chunk_unless_reraised():
    async def run(emit) -> ToolTurn:
        raise WorkbenchError(400, "invalid_output_schema", "bad schema")

    (failed,) = _collect_turn(run)
    assert failed.done is True
    assert "bad schema" in failed.error

    # A backend whose setup errors must surface as a 400 opts out per type.
    with pytest.raises(WorkbenchError):
        _collect_turn(run, reraise=(WorkbenchError,))
