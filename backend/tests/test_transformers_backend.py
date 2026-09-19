import asyncio
from typing import ClassVar

import pytest
import torch

from app.inference import transformers_backend
from app.inference.schemas import ChatChunk, ChatMessage
from app.inference.transformers_backend import TransformersBackend


class _FakeEncoding(dict):
    def to(self, device):
        self["device"] = device
        return self


class _FakeTokenizer:
    instances: ClassVar[list] = []

    def __init__(self) -> None:
        self.snapshot_dir = None
        self.applied_messages = None
        _FakeTokenizer.instances.append(self)

    @classmethod
    def from_pretrained(cls, snapshot_dir):
        instance = cls()
        instance.snapshot_dir = snapshot_dir
        return instance

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs["add_generation_prompt"] is True
        self.applied_messages = messages
        return _FakeEncoding(input_ids=[[1, 2]])


class _FakeStreamer:
    def __init__(self, tokenizer, skip_prompt=False) -> None:
        assert skip_prompt is True
        self._texts = iter(["Hel", "", "lo"])
        self.ended = False

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._texts)

    def end(self):
        self.ended = True


class _FakeModel:
    instances: ClassVar[list] = []

    def __init__(self) -> None:
        self.snapshot_dir = None
        self.load_kwargs = {}
        self.device = None
        _FakeModel.instances.append(self)

    @classmethod
    def from_pretrained(cls, snapshot_dir, **kwargs):
        instance = cls()
        instance.snapshot_dir = snapshot_dir
        instance.load_kwargs = kwargs
        return instance

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        return self

    def generate(self, **kwargs):
        return None


@pytest.fixture(autouse=True)
def _clear_cache():
    transformers_backend._CACHE.clear()
    _FakeTokenizer.instances.clear()
    _FakeModel.instances.clear()
    yield
    transformers_backend._CACHE.clear()
    _FakeTokenizer.instances.clear()
    _FakeModel.instances.clear()


def _install_fakes(monkeypatch) -> None:
    monkeypatch.setattr(transformers_backend, "AutoTokenizer", _FakeTokenizer)
    monkeypatch.setattr(transformers_backend, "AutoModelForCausalLM", _FakeModel)
    monkeypatch.setattr(transformers_backend, "TextIteratorStreamer", _FakeStreamer)


def _run_stream_chat(backend: TransformersBackend) -> list[ChatChunk]:
    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="hi")]
        return [chunk async for chunk in backend.stream_chat("org/model", messages)]

    return asyncio.run(_collect())


def test_capabilities_report_guided_and_native_tool_calling():
    backend = TransformersBackend("/tmp/snapshot")

    capabilities = backend.capabilities()

    assert capabilities.structured_output_mode == "guided"
    assert capabilities.native_tool_calling is True


def test_stream_chat_yields_deltas_then_a_terminal_done_chunk(monkeypatch):
    _install_fakes(monkeypatch)
    backend = TransformersBackend("/tmp/snapshot")

    chunks = _run_stream_chat(backend)

    # An empty text piece is skipped, not surfaced as an empty delta.
    assert [c.delta for c in chunks] == ["Hel", "lo", ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
    # The chat messages reach the template, and weights land on the detected device.
    assert _FakeTokenizer.instances[0].applied_messages == [
        {"role": "user", "content": "hi"}
    ]
    assert _FakeModel.instances[0].device == backend._device


def test_stream_chat_converts_generation_error_to_a_terminal_error_chunk(monkeypatch):
    class _BoomModel(_FakeModel):
        def generate(self, **kwargs):
            raise RuntimeError("boom")

    _install_fakes(monkeypatch)
    monkeypatch.setattr(transformers_backend, "AutoModelForCausalLM", _BoomModel)
    backend = TransformersBackend("/tmp/snapshot")

    chunks = _run_stream_chat(backend)

    # Deltas streamed before the crash are kept; what matters is the stream
    # terminates with the error instead of hanging.
    assert chunks[-1].done is True
    assert "boom" in chunks[-1].error


def test_stream_chat_names_the_snapshot_when_loading_fails(monkeypatch):
    class _MissingModel(_FakeModel):
        @classmethod
        def from_pretrained(cls, snapshot_dir, **kwargs):
            raise OSError("no such directory")

    _install_fakes(monkeypatch)
    monkeypatch.setattr(transformers_backend, "AutoModelForCausalLM", _MissingModel)
    backend = TransformersBackend("/tmp/gone")

    chunks = _run_stream_chat(backend)

    assert len(chunks) == 1
    assert chunks[0].done is True
    assert "/tmp/gone" in chunks[0].error


@pytest.mark.parametrize(
    ("mps", "cuda", "expected_device", "expected_dtype"),
    [
        (True, True, "mps", torch.float16),
        (False, True, "cuda", torch.float16),
        (False, False, "cpu", torch.float32),
    ],
)
def test_device_selection_prefers_mps_then_cuda_then_cpu(
    monkeypatch, mps, cuda, expected_device, expected_dtype
):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(
        transformers_backend.torch.backends.mps, "is_available", lambda: mps
    )
    monkeypatch.setattr(
        transformers_backend.torch.cuda, "is_available", lambda: cuda
    )
    backend = TransformersBackend("/tmp/snapshot")

    model, _ = backend._get_model()

    assert backend._device == expected_device
    assert model.device == expected_device
    assert model.load_kwargs["torch_dtype"] == expected_dtype
    assert model.load_kwargs["trust_remote_code"] is False
