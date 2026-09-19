import asyncio

import pytest

from app.inference import llama_cpp_backend
from app.inference.llama_cpp_backend import LlamaCppBackend
from app.inference.schemas import ChatChunk, ChatMessage

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
