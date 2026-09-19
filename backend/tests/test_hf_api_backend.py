import asyncio
from types import SimpleNamespace

import httpx
import pytest
from huggingface_hub.errors import BadRequestError

from app.inference.hf_api_backend import HFInferenceAPIBackend
from app.inference.schemas import ChatChunk, ChatMessage
from app.tools import get_tool


def _tools():
    return [get_tool("calculator").spec]


def _completion_chunk(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


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


def _non_streamed_completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


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
