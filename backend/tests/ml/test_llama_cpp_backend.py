import asyncio
import json

import pytest

from app.inference import llama_cpp_backend
from app.inference.llama_cpp_backend import LlamaCppBackend
from app.inference.schemas import ChatChunk, ChatMessage
from app.tools import get_tool

pytestmark = pytest.mark.ml


@pytest.fixture(autouse=True)
def _clear_cache():
    llama_cpp_backend._CACHE.clear()
    yield
    llama_cpp_backend._CACHE.clear()


class _FakeLlama:
    def __init__(self, model_path: str, verbose: bool = False) -> None:
        self.model_path = model_path

    def create_chat_completion(self, messages, stream=True):
        assert stream is True
        return iter(
            [
                {"choices": [{"delta": {"content": "Hel"}}]},
                {"choices": [{"delta": {}}]},
                {"choices": [{"delta": {"content": "lo"}}]},
            ]
        )


def _run_stream_chat(backend: LlamaCppBackend) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="hi")]
        return [chunk async for chunk in backend.stream_chat("whatever/model", messages)]

    return asyncio.run(_collect())


def _run_tool_chat(backend: LlamaCppBackend) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="What is 2 + 3?")]
        tools = [get_tool("calculator").spec]
        return [chunk async for chunk in backend.stream_chat("whatever/model", messages, tools=tools)]

    return asyncio.run(_collect())


def test_capabilities_report_grammar_and_native_tool_calling():
    backend = LlamaCppBackend("/tmp/fake.gguf")

    capabilities = backend.capabilities()

    assert capabilities.structured_output_mode == "grammar"
    assert capabilities.native_tool_calling is True


def test_stream_chat_yields_deltas_then_a_terminal_done_chunk(monkeypatch):
    monkeypatch.setattr(llama_cpp_backend, "Llama", _FakeLlama)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    chunks = _run_stream_chat(backend)

    # A content-less delta (e.g. a role-only chunk) is skipped, not surfaced empty.
    assert [c.delta for c in chunks] == ["Hel", "lo", ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None


def test_stream_chat_converts_generation_error_to_a_terminal_error_chunk(monkeypatch):
    class _BoomLlama(_FakeLlama):
        def create_chat_completion(self, messages, stream=True):
            raise RuntimeError("boom")

    monkeypatch.setattr(llama_cpp_backend, "Llama", _BoomLlama)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    chunks = _run_stream_chat(backend)

    assert len(chunks) == 1
    assert chunks[0].done is True
    assert "boom" in chunks[0].error


def test_stream_chat_names_the_model_when_loading_fails(monkeypatch):
    class _MissingLlama(_FakeLlama):
        def __init__(self, model_path: str, verbose: bool = False) -> None:
            raise OSError("file does not exist")

    monkeypatch.setattr(llama_cpp_backend, "Llama", _MissingLlama)
    backend = LlamaCppBackend("/tmp/gone.gguf")

    chunks = _run_stream_chat(backend)

    assert len(chunks) == 1
    assert chunks[0].done is True
    assert "/tmp/gone.gguf" in chunks[0].error


def _tool_call_message(call_id: str, name: str, arguments) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


class _FakeToolLlama(_FakeLlama):
    """First non-streamed turn requests a calculator call, the second answers."""

    def __init__(self, model_path: str, verbose: bool = False) -> None:
        super().__init__(model_path, verbose)
        self.seen: list[list[dict]] = []

    def create_chat_completion(self, messages, stream=True, tools=None, tool_choice=None):
        assert stream is False
        assert tool_choice == "auto"
        # OpenAI tool shape -- what llama-cpp-python actually reads (tool["function"]).
        assert [t["function"]["name"] for t in tools] == ["calculator"]
        assert all(t["type"] == "function" for t in tools)
        self.seen.append(list(messages))
        if len(self.seen) == 1:
            return {
                "choices": [
                    {
                        "message": _tool_call_message(
                            "call_1", "calculator", json.dumps({"expression": "2 + 3"})
                        )
                    }
                ]
            }
        return {"choices": [{"message": {"role": "assistant", "content": "5"}}]}


def test_stream_chat_with_tools_executes_the_call_and_streams_the_final_text(monkeypatch):
    monkeypatch.setattr(llama_cpp_backend, "Llama", _FakeToolLlama)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    chunks = _run_tool_chat(backend)

    # Tools mode never streams partial turns: one delta + done.
    assert [c.delta for c in chunks] == ["5", ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
    # The real calculator ran: its result rode back as a tool-role message.
    llama = llama_cpp_backend._CACHE["/tmp/fake.gguf"]
    tool_messages = [m for m in llama.seen[-1] if m["role"] == "tool"]
    assert tool_messages == [{"role": "tool", "tool_call_id": "call_1", "content": "5"}]


class _FakeStubbornLlama(_FakeLlama):
    """Always requests a tool call, so the loop exhausts its model turns."""

    def create_chat_completion(self, messages, stream=True, tools=None, tool_choice=None):
        assert stream is False
        return {"choices": [{"message": _tool_call_message("call_1", "calculator", {})}]}


def test_stream_chat_with_tools_returns_empty_when_turns_run_out(monkeypatch):
    monkeypatch.setattr(llama_cpp_backend, "Llama", _FakeStubbornLlama)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    chunks = _run_tool_chat(backend)

    assert [c.delta for c in chunks] == ["", ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None


class _FakePlainTextToolLlama(_FakeLlama):
    """Small models emit the tool attempt as plain-text <tool_call> JSON."""

    def __init__(self, model_path: str, verbose: bool = False) -> None:
        super().__init__(model_path, verbose)
        self.seen: list[list[dict]] = []

    def create_chat_completion(self, messages, stream=True, tools=None, tool_choice=None):
        assert stream is False
        self.seen.append(list(messages))
        if len(self.seen) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '<tool_call>\n{"name": "calculator", '
                            '"arguments": {"expression": "6 * 7"}}\n</tool_call>',
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"role": "assistant", "content": "42"}}]}


def test_stream_chat_with_tools_executes_plain_text_tool_call(monkeypatch):
    monkeypatch.setattr(llama_cpp_backend, "Llama", _FakePlainTextToolLlama)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    chunks = _run_tool_chat(backend)

    assert [c.delta for c in chunks] == ["42", ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
    llama = llama_cpp_backend._CACHE["/tmp/fake.gguf"]
    tool_messages = [m for m in llama.seen[-1] if m["role"] == "tool"]
    assert tool_messages == [{"role": "tool", "tool_call_id": "", "content": "42"}]
