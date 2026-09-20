import asyncio
from types import SimpleNamespace

import httpx
import pytest
from huggingface_hub.errors import BadRequestError

from app.errors import WorkbenchError
from app.inference.hf_api_backend import HFInferenceAPIBackend
from app.inference.schemas import ChatChunk, ChatMessage
from app.tools import get_tool


def _tools():
    return [get_tool("calculator").spec]


def _completion_chunk(content: str | None, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))], usage=usage
    )


def _usage_chunk(prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    """The terminal usage-only chunk stream_options={"include_usage": True} adds --
    empty choices, per the OpenAI-compatible streaming convention."""
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


async def _fake_stream(chunks: list[SimpleNamespace]):
    for chunk in chunks:
        yield chunk


def _run_stream_chat(backend: HFInferenceAPIBackend) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="hi")]
        return [chunk async for chunk in backend.stream_chat("some/model", messages)]

    return asyncio.run(_collect())


def _run_tool_chat(backend: HFInferenceAPIBackend) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="What is 2 + 3?")]
        return [chunk async for chunk in backend.stream_chat("some/model", messages, tools=_tools())]

    return asyncio.run(_collect())


def test_capabilities_report_prompt_retry_and_no_native_tool_calling():
    backend = HFInferenceAPIBackend(api_key="fake-key")

    capabilities = backend.capabilities()

    assert capabilities.structured_output_mode == "prompt_retry"
    assert capabilities.native_tool_calling is False


def test_stream_chat_yields_deltas_then_a_terminal_done_chunk(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")

    async def fake_chat_completion(**kwargs):
        # A None-content delta (e.g. a role-only or reasoning-only chunk) should be
        # skipped rather than surfaced as an empty delta.
        return _fake_stream(
            [_completion_chunk("Hel"), _completion_chunk("lo"), _completion_chunk(None)]
        )

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_stream_chat(backend)

    # Trailing "" is the terminal done chunk; a None-content delta leaking through
    # would show up as an extra empty delta here.
    assert [c.delta for c in chunks] == ["Hel", "lo", ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None


def test_stream_chat_converts_hf_error_to_a_terminal_error_chunk(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")

    async def fake_chat_completion(**kwargs):
        response = httpx.Response(
            400, request=httpx.Request("POST", "https://router.huggingface.co")
        )
        raise BadRequestError("model not supported by any provider", response=response)

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_stream_chat(backend)

    assert len(chunks) == 1
    assert chunks[0].done is True
    assert "not supported" in chunks[0].error


def _non_streamed_completion(content: str, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage
    )


def test_stream_chat_with_tools_runs_the_fallback_loop(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")
    sent_messages = []

    async def fake_chat_completion(**kwargs):
        assert kwargs["stream"] is False
        sent_messages.append(kwargs["messages"])
        if len(sent_messages) == 1:
            return _non_streamed_completion(
                '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}'
            )
        return _non_streamed_completion('{"reply": "the answer is 5"}')

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_tool_chat(backend)

    # The whole loop resolves to one delta + done (tools mode never streams).
    assert [c.delta for c in chunks] == ['{"reply": "the answer is 5"}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
    # The real calculator ran and its result reached the model on the next turn.
    assert any(
        "Tool 'calculator' returned: 5" in m["content"] for m in sent_messages[-1]
    )


def test_stream_chat_with_tools_converts_hf_error_to_a_terminal_error_chunk(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")

    async def fake_chat_completion(**kwargs):
        response = httpx.Response(
            400, request=httpx.Request("POST", "https://router.huggingface.co")
        )
        raise BadRequestError("model not supported by any provider", response=response)

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_tool_chat(backend)

    assert len(chunks) == 1
    assert chunks[0].done is True
    assert "not supported" in chunks[0].error


@pytest.mark.network
def test_stream_chat_against_real_hf_inference_api():
    from app.config import get_settings

    backend = HFInferenceAPIBackend(api_key=get_settings().hf_api_key)
    messages = [ChatMessage(role="user", content="Say hi in exactly one word.")]

    async def _collect() -> list[ChatChunk]:
        return [chunk async for chunk in backend.stream_chat("openai/gpt-oss-20b", messages)]

    chunks = asyncio.run(_collect())

    assert chunks[-1].done is True
    assert chunks[-1].error is None


_SCHEMA = {
    "type": "object",
    "required": ["answer"],
    "properties": {"answer": {"type": "integer"}},
}


def _run_schema_chat(
    backend: HFInferenceAPIBackend, schema: dict, tools=None
) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="Answer with JSON.")]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "some/model", messages, tools=tools, output_schema=schema
            )
        ]

    return asyncio.run(_collect())


def test_stream_chat_with_schema_returns_valid_json_first_try(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")

    async def fake_chat_completion(**kwargs):
        assert kwargs["stream"] is False
        return _non_streamed_completion('Sure: {"answer": 42}')

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_schema_chat(backend, _SCHEMA)

    # One delta + done; the delta is pure JSON even when the model adds chatter.
    assert [c.delta for c in chunks] == ['{"answer": 42}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None


def test_stream_chat_with_schema_retries_garbage_then_succeeds(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")
    sent_messages = []

    async def fake_chat_completion(**kwargs):
        sent_messages.append(kwargs["messages"])
        if len(sent_messages) == 1:
            return _non_streamed_completion("no json here at all")
        return _non_streamed_completion('{"answer": 7}')

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_schema_chat(backend, _SCHEMA)

    assert [c.delta for c in chunks] == ['{"answer": 7}', ""]
    assert chunks[-1].done is True
    # The retry fed error feedback back before the successful turn.
    assert any(
        "required schema" in m["content"] for m in sent_messages[-1] if m["role"] == "user"
    )


def test_stream_chat_with_schema_returns_last_text_when_turns_run_out(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")
    calls = []

    async def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return _non_streamed_completion("still not json")

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_schema_chat(backend, _SCHEMA)

    # Exhausted turns are a terminal chunk with the last text, never raised.
    assert len(calls) == 5
    assert [c.delta for c in chunks] == ["still not json", ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None


def test_stream_chat_with_tools_and_schema_skips_schema_loop_when_draft_conforms(
    monkeypatch,
):
    backend = HFInferenceAPIBackend(api_key="fake-key")
    script = [
        '{"tool": "calculator", "arguments": {"expression": "6 * 7"}}',
        '{"answer": 42}',
        '{"answer": 42}',
        '{"answer": 42}',
        '{"answer": 42}',
    ]
    calls = []

    async def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return _non_streamed_completion(script.pop(0))

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_schema_chat(backend, _SCHEMA, tools=_tools())

    # The tool loop's draft already conformed, so no schema-loop turn ran:
    # five tool-loop turns, zero schema-loop turns.
    assert [c.delta for c in chunks] == ['{"answer": 42}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
    assert len(calls) == 5


def test_stream_chat_with_tools_and_schema_constrains_the_final_reply(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")
    script = [
        '{"tool": "calculator", "arguments": {"expression": "6 * 7"}}',
        '{"reply": "the answer is 42"}',
        'Here you go: {"answer": 42}',
    ]

    async def fake_chat_completion(**kwargs):
        return _non_streamed_completion(script.pop(0))

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_schema_chat(backend, _SCHEMA, tools=_tools())

    # Tool loop ran first (calculator), then the final reply was schema-shaped.
    assert [c.delta for c in chunks] == ['{"answer": 42}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None


def test_stream_chat_with_invalid_schema_raises_pre_stream():
    backend = HFInferenceAPIBackend(api_key="fake-key")

    async def _collect() -> None:
        messages = [ChatMessage(role="user", content="hi")]
        with pytest.raises(WorkbenchError) as exc_info:
            async for _ in backend.stream_chat(
                "some/model", messages, output_schema=["not", "a", "dict"]
            ):
                pass
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_output_schema"

    asyncio.run(_collect())


def test_stream_chat_requests_usage_and_captures_it_from_the_final_chunk(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")

    async def fake_chat_completion(**kwargs):
        assert kwargs["stream_options"] == {"include_usage": True}
        return _fake_stream(
            [
                _completion_chunk("Hel"),
                _completion_chunk("lo"),
                _usage_chunk(prompt_tokens=12, completion_tokens=2),
            ]
        )

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_stream_chat(backend)

    # The usage-only chunk has empty choices -- it must not add a spurious delta.
    assert [c.delta for c in chunks] == ["Hel", "lo", ""]
    assert chunks[-1].usage.prompt_tokens == 12
    assert chunks[-1].usage.completion_tokens == 2


def test_stream_chat_with_tools_reports_tools_called_and_summed_usage(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")
    sent_messages = []

    async def fake_chat_completion(**kwargs):
        sent_messages.append(kwargs["messages"])
        if len(sent_messages) == 1:
            return _non_streamed_completion(
                '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
                usage=SimpleNamespace(prompt_tokens=20, completion_tokens=15, total_tokens=35),
            )
        return _non_streamed_completion(
            '{"reply": "the answer is 5"}',
            usage=SimpleNamespace(prompt_tokens=40, completion_tokens=5, total_tokens=45),
        )

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_tool_chat(backend)

    assert chunks[-1].tools_called == ["calculator"]
    # completion_tokens sums across both turns; prompt_tokens is the last turn's
    # (it already includes the full accumulated history).
    assert chunks[-1].usage.completion_tokens == 20
    assert chunks[-1].usage.prompt_tokens == 40


def test_stream_chat_with_schema_first_try_reports_zero_retries(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")

    async def fake_chat_completion(**kwargs):
        return _non_streamed_completion('{"answer": 42}')

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_schema_chat(backend, _SCHEMA)

    assert chunks[-1].retries == 0


def test_stream_chat_with_schema_retry_reports_nonzero_retries(monkeypatch):
    backend = HFInferenceAPIBackend(api_key="fake-key")
    sent_messages = []

    async def fake_chat_completion(**kwargs):
        sent_messages.append(kwargs["messages"])
        if len(sent_messages) == 1:
            return _non_streamed_completion("no json here at all")
        return _non_streamed_completion('{"answer": 7}')

    monkeypatch.setattr(backend._client, "chat_completion", fake_chat_completion)

    chunks = _run_schema_chat(backend, _SCHEMA)

    assert chunks[-1].retries == 1
