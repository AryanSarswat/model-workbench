import asyncio
import json

import pytest
from llama_cpp import LlamaGrammar

from app.errors import WorkbenchError
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


_SCHEMA = {
    "type": "object",
    "required": ["answer"],
    "properties": {"answer": {"type": "integer"}},
}


def _run_schema_chat(
    backend: LlamaCppBackend, schema: dict, tools=None
) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="hi")]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "whatever/model", messages, tools=tools, output_schema=schema
            )
        ]

    return asyncio.run(_collect())


class _FakeSchemaLlama(_FakeLlama):
    """Records kwargs so tests can assert on the grammar kwarg."""

    def __init__(self, model_path: str, verbose: bool = False) -> None:
        super().__init__(model_path, verbose)
        self.seen_kwargs: dict = {}

    def create_chat_completion(self, messages, stream=True, **kwargs):
        assert stream is True
        self.seen_kwargs = kwargs
        return iter(
            [
                {"choices": [{"delta": {"content": '{"answer":'}}]},
                {"choices": [{"delta": {"content": " 42}"}}]},
            ]
        )


def test_stream_chat_with_schema_passes_grammar_and_yields_single_delta(monkeypatch):
    fake = _FakeSchemaLlama("/tmp/fake.gguf")
    monkeypatch.setattr(LlamaCppBackend, "_get_llama", lambda self: fake)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    chunks = _run_schema_chat(backend, _SCHEMA)

    assert isinstance(fake.seen_kwargs.get("grammar"), LlamaGrammar)
    # Constrained turns never stream fragments: one delta + done.
    assert [c.delta for c in chunks] == ['{"answer": 42}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None


def test_stream_chat_without_schema_passes_no_grammar(monkeypatch):
    fake = _FakeSchemaLlama("/tmp/fake.gguf")
    monkeypatch.setattr(LlamaCppBackend, "_get_llama", lambda self: fake)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    chunks = _run_stream_chat(backend)

    assert "grammar" not in fake.seen_kwargs
    assert [c.delta for c in chunks] == ['{"answer":', " 42}", ""]
    assert chunks[-1].done is True


def test_stream_chat_with_invalid_schema_raises_pre_stream():
    backend = LlamaCppBackend("/tmp/fake.gguf")

    async def _collect() -> None:
        messages = [ChatMessage(role="user", content="hi")]
        with pytest.raises(WorkbenchError) as exc_info:
            async for _ in backend.stream_chat(
                "whatever/model", messages, output_schema={"type": 42}
            ):
                pass
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_output_schema"

    asyncio.run(_collect())


class _FakeSchemaToolLlama(_FakeLlama):
    """One native tool turn, then a final answer -- every turn must carry grammar."""

    def __init__(self, model_path: str, verbose: bool = False) -> None:
        super().__init__(model_path, verbose)
        self.grammars: list = []
        self.turns = 0

    def create_chat_completion(
        self, messages, stream=True, tools=None, tool_choice=None, **kwargs
    ):
        assert stream is False
        self.grammars.append(kwargs.get("grammar"))
        self.turns += 1
        if self.turns == 1:
            return {
                "choices": [
                    {
                        "message": _tool_call_message(
                            "call_1", "calculator", json.dumps({"expression": "2 + 3"})
                        )
                    }
                ]
            }
        return {"choices": [{"message": {"role": "assistant", "content": '{"answer": 5}'}}]}


def test_stream_chat_with_tools_and_schema_constrains_every_turn(monkeypatch):
    fake = _FakeSchemaToolLlama("/tmp/fake.gguf")
    monkeypatch.setattr(LlamaCppBackend, "_get_llama", lambda self: fake)
    backend = LlamaCppBackend("/tmp/fake.gguf")

    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="What is 2 + 3?")]
        tools = [get_tool("calculator").spec]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "whatever/model", messages, tools=tools, output_schema=_SCHEMA
            )
        ]

    chunks = asyncio.run(_collect())

    assert len(fake.grammars) == 2
    assert all(isinstance(g, LlamaGrammar) for g in fake.grammars)
    assert [c.delta for c in chunks] == ['{"answer": 5}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
