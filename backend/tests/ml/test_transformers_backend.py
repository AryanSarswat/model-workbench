import asyncio
import json
import sys
from typing import ClassVar

import pytest
import torch
from transformers import LogitsProcessorList

from app.errors import WorkbenchError
from app.inference import transformers_backend
from app.inference.schemas import ChatChunk, ChatMessage
from app.inference.transformers_backend import TransformersBackend
from app.tools import get_tool

pytestmark = pytest.mark.ml


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

    def __call__(self, text, **kwargs):
        # One "token" per whitespace-separated word -- good enough to test the
        # wiring, not a real tokenizer.
        return {"input_ids": text.split()}


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


def test_stream_chat_with_tools_runs_the_fallback_loop(monkeypatch):
    scripted = iter(
        [
            '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
            '{"reply": "the answer is 5"}',
        ]
    )
    prompts = []

    class _ToolTokenizer(_FakeTokenizer):
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["add_generation_prompt"] is True
            assert kwargs["tokenize"] is False
            self.applied_messages = messages
            return "BASE PROMPT"

        def __call__(self, text, **kwargs):
            prompts.append(text)
            return _FakeEncoding(input_ids=[[1, 2]])

        def decode(self, ids, **kwargs):
            assert kwargs["skip_special_tokens"] is True
            return next(scripted)

    class _ToolModel(_FakeModel):
        def generate(self, **kwargs):
            assert "streamer" not in kwargs
            assert kwargs.get("max_new_tokens") == 512
            self.generate_kwargs = kwargs
            return [[1, 2, 3, 4]]

    _install_fakes(monkeypatch)
    monkeypatch.setattr(transformers_backend, "AutoTokenizer", _ToolTokenizer)
    monkeypatch.setattr(transformers_backend, "AutoModelForCausalLM", _ToolModel)
    backend = TransformersBackend("/tmp/snapshot")

    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="What is 2 + 3?")]
        tools = [get_tool("calculator").spec]
        return [chunk async for chunk in backend.stream_chat("org/model", messages, tools=tools)]

    chunks = asyncio.run(_collect())

    # The whole loop resolves to one delta + done (tools mode never streams).
    assert [c.delta for c in chunks] == ['{"reply": "the answer is 5"}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
    # The prompt was templated once, and the calculator result fed the next turn.
    assert _ToolTokenizer.instances[0].applied_messages[0]["role"] == "system"
    assert any("Tool 'calculator' returned: 5" in prompt for prompt in prompts)
    assert chunks[-1].tools_called == ["calculator"]
    assert chunks[-1].usage.prompt_tokens == 2  # every _FakeEncoding uses input_ids=[[1, 2]]
    assert chunks[-1].usage.completion_tokens == 4  # 2 generate() turns x 2 completion tokens each


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
    assert chunks[-1].usage.prompt_tokens == 2  # input_ids=[[1, 2]] from _FakeEncoding
    assert chunks[-1].usage.completion_tokens == 1  # "Hello".split() -> one token


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


class _GuidedTokenizer(_FakeTokenizer):
    """Fake serving scripted replies per generate turn, recording prompts."""

    def __init__(self, replies: list[str]) -> None:
        super().__init__()
        self._replies = list(replies)
        self.prompts: list[str] = []

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs["add_generation_prompt"] is True
        self.applied_messages = messages
        if kwargs.get("tokenize") is False:
            return "BASE PROMPT"
        return _FakeEncoding(input_ids=[[1, 2]])

    def __call__(self, text, **kwargs):
        self.prompts.append(text)
        return _FakeEncoding(input_ids=[[1, 2]])

    def decode(self, ids, **kwargs):
        return self._replies.pop(0)


class _GuidedModel(_FakeModel):
    def __init__(self) -> None:
        super().__init__()
        self.generate_calls: list[dict] = []

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return [[1, 2, 3, 4]]


def _real_tokenizer():
    """A tiny real fast tokenizer built locally (no Hub download), enough for
    outlines' from_transformers wrapper and vocabulary indexing."""
    pytest.importorskip("tokenizers")
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import PreTrainedTokenizerFast

    tok = Tokenizer(
        WordLevel(
            vocab={
                "[UNK]": 0,
                "[EOS]": 1,
                "hello": 2,
                "{": 3,
                "}": 4,
                '"': 5,
                "a": 6,
                ":": 7,
                "1": 8,
                " ": 9,
            },
            unk_token="[UNK]",
        )
    )
    tok.pre_tokenizer = Whitespace()
    return PreTrainedTokenizerFast(
        tokenizer_object=tok, unk_token="[UNK]", eos_token="[EOS]"
    )


def _patch_guided_processor(monkeypatch, sentinel=None):
    sentinel = sentinel if sentinel is not None else object()
    built: list = []

    def _fake_build(model, tokenizer, schema):
        built.append((model, tokenizer, schema))
        return sentinel

    monkeypatch.setattr(transformers_backend, "_build_guided_processor", _fake_build)
    return sentinel, built


def test_guided_plain_path_yields_single_delta_with_processor(monkeypatch):
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    model, tokenizer = _GuidedModel(), _GuidedTokenizer(['{"a": 1}'])
    backend = TransformersBackend("/tmp/snapshot")
    monkeypatch.setattr(backend, "_get_model", lambda: (model, tokenizer))
    sentinel, built = _patch_guided_processor(monkeypatch)

    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="hi")]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "org/model", messages, output_schema=schema
            )
        ]

    chunks = asyncio.run(_collect())

    # Constrained turns never stream: one delta + done.
    assert [c.delta for c in chunks] == ['{"a": 1}', ""]
    assert chunks[-1].done is True
    assert chunks[-1].error is None
    assert model.generate_calls[0].get("max_new_tokens") == 512
    processor = model.generate_calls[0].get("logits_processor")
    assert isinstance(processor, LogitsProcessorList)
    assert list(processor) == [sentinel]
    assert built == [(model, tokenizer, schema)]
    assert chunks[-1].usage.prompt_tokens == 2
    assert chunks[-1].usage.completion_tokens == 2  # outputs[0][input_len:] == [3, 4]


def test_plain_path_without_schema_passes_no_logits_processor(monkeypatch):
    model, tokenizer = _GuidedModel(), _GuidedTokenizer([])
    backend = TransformersBackend("/tmp/snapshot")
    monkeypatch.setattr(backend, "_get_model", lambda: (model, tokenizer))
    monkeypatch.setattr(transformers_backend, "TextIteratorStreamer", _FakeStreamer)

    chunks = _run_stream_chat(backend)

    assert chunks[-1].done is True
    assert "logits_processor" not in model.generate_calls[0]


def test_guided_tool_loop_constrains_only_the_final_turn(monkeypatch):
    scripted = [
        '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
        '{"reply": "the answer is 5"}',
        '{"answer": 5}',
    ]
    schema = {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }
    model, tokenizer = _GuidedModel(), _GuidedTokenizer(scripted)
    backend = TransformersBackend("/tmp/snapshot")
    monkeypatch.setattr(backend, "_get_model", lambda: (model, tokenizer))
    sentinel, built = _patch_guided_processor(monkeypatch)

    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="What is 2 + 3?")]
        tools = [get_tool("calculator").spec]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "org/model", messages, tools=tools, output_schema=schema
            )
        ]

    chunks = asyncio.run(_collect())

    assert [c.delta for c in chunks] == ['{"answer": 5}', ""]
    assert chunks[-1].done is True
    # Two unconstrained loop turns, then one guided final turn.
    assert len(model.generate_calls) == 3
    assert "logits_processor" not in model.generate_calls[0]
    assert "logits_processor" not in model.generate_calls[1]
    assert list(model.generate_calls[2]["logits_processor"]) == [sentinel]
    assert built == [(model, tokenizer, schema)]
    # Tool results reached the guided turn's context.
    assert any("Tool 'calculator' returned: 5" in prompt for prompt in tokenizer.prompts)
    assert chunks[-1].tools_called == ["calculator"]
    assert chunks[-1].usage.completion_tokens == 6  # 3 generate() turns x 2 completion tokens each


def test_invalid_output_schema_raises_400_pre_stream(monkeypatch):
    pytest.importorskip("outlines")
    model, tokenizer = _FakeModel(), _real_tokenizer()
    backend = TransformersBackend("/tmp/snapshot")
    monkeypatch.setattr(backend, "_get_model", lambda: (model, tokenizer))

    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="hi")]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "org/model", messages, output_schema={"type": "not_a_real_type"}
            )
        ]

    with pytest.raises(WorkbenchError) as exc_info:
        asyncio.run(_collect())

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_output_schema"


def test_prevalidate_output_schema_rejects_bad_type_without_a_model():
    pytest.importorskip("outlines_core")
    backend = TransformersBackend("/tmp/snapshot")

    with pytest.raises(WorkbenchError) as exc_info:
        backend.prevalidate_output_schema({"type": "not_a_real_type"})

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_output_schema"


def test_prevalidate_output_schema_accepts_valid_schema():
    pytest.importorskip("outlines_core")
    backend = TransformersBackend("/tmp/snapshot")

    backend.prevalidate_output_schema(
        {"type": "object", "properties": {"a": {"type": "integer"}}}
    )


def test_missing_outlines_raises_backend_not_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "outlines", None)
    monkeypatch.setitem(sys.modules, "outlines.backends", None)

    with pytest.raises(WorkbenchError) as exc_info:
        transformers_backend._build_guided_processor(
            object(), object(), {"type": "object"}
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "backend_not_available"


def _conforming_schema() -> dict:
    return {
        "type": "object",
        "required": ["answer"],
        "properties": {"answer": {"type": "integer"}},
    }


def test_tool_loop_conforming_draft_skips_guided_turn(monkeypatch):
    # After the tool call the model emits the schema-shaped answer directly;
    # the loop treats it as a non-tool turn and retries, so all five loop
    # turns run -- but the conforming draft returns as-is, no guided turn.
    scripted = [
        '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
        '{"answer": 5}',
        '{"answer": 5}',
        '{"answer": 5}',
        '{"answer": 5}',
    ]
    schema = _conforming_schema()
    model, tokenizer = _GuidedModel(), _GuidedTokenizer(scripted)
    backend = TransformersBackend("/tmp/snapshot")
    monkeypatch.setattr(backend, "_get_model", lambda: (model, tokenizer))
    _, built = _patch_guided_processor(monkeypatch)

    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="What is 2 + 3?")]
        tools = [get_tool("calculator").spec]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "org/model", messages, tools=tools, output_schema=schema
            )
        ]

    chunks = asyncio.run(_collect())

    assert [c.delta for c in chunks] == ['{"answer": 5}', ""]
    assert chunks[-1].done is True
    assert len(model.generate_calls) == 5
    assert all("logits_processor" not in call for call in model.generate_calls)
    assert built == []
    # The schema instruction rode the single template-built prompt.
    assert json.dumps(schema) in tokenizer.applied_messages[0]["content"]


def test_tool_loop_nonconforming_draft_falls_through_to_guided(monkeypatch):
    scripted = [
        '{"tool": "calculator", "arguments": {"expression": "2 + 3"}}',
        '{"wrong": 1}',
        '{"wrong": 1}',
        '{"wrong": 1}',
        '{"wrong": 1}',
        '{"answer": 5}',
    ]
    schema = _conforming_schema()
    model, tokenizer = _GuidedModel(), _GuidedTokenizer(scripted)
    backend = TransformersBackend("/tmp/snapshot")
    monkeypatch.setattr(backend, "_get_model", lambda: (model, tokenizer))
    sentinel, built = _patch_guided_processor(monkeypatch)

    async def _collect() -> list[ChatChunk]:
        messages = [ChatMessage(role="user", content="What is 2 + 3?")]
        tools = [get_tool("calculator").spec]
        return [
            chunk
            async for chunk in backend.stream_chat(
                "org/model", messages, tools=tools, output_schema=schema
            )
        ]

    chunks = asyncio.run(_collect())

    assert [c.delta for c in chunks] == ['{"answer": 5}', ""]
    assert chunks[-1].done is True
    # Five loop turns plus the guided final turn.
    assert len(model.generate_calls) == 6
    assert list(model.generate_calls[-1]["logits_processor"]) == [sentinel]
    assert built == [(model, tokenizer, schema)]
