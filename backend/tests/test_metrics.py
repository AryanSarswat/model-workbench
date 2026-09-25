from unittest.mock import patch

from app.config import MemoryUsage
from app.inference.schemas import ChatChunk, TokenUsage
from app.metrics import TurnRecorder, build_response_metric


def _patched_memory():
    return patch(
        "app.metrics.get_memory_usage",
        return_value=MemoryUsage(ram_used_gb=8.0, vram_used_gb=None),
    )


def test_build_response_metric_computes_latency_ttft_and_tokens_per_sec():
    with _patched_memory():
        metric = build_response_metric(
            model_id="some/model",
            backend_name="api",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
            started_at=0.0,
            first_chunk_at=0.1,
            finished_at=1.0,
        )

    assert metric.model_id == "some/model"
    assert metric.backend == "api"
    assert metric.prompt_tokens == 10
    assert metric.completion_tokens == 20
    assert metric.latency_ms == 1000.0
    assert metric.ttft_ms == 100.0
    assert metric.tokens_per_sec == 20.0
    assert metric.cost_usd is None
    assert metric.ram_used_gb == 8.0
    assert metric.vram_used_gb is None


def test_build_response_metric_zero_completion_tokens_yields_no_rate():
    with _patched_memory():
        metric = build_response_metric(
            model_id="some/model",
            backend_name="api",
            usage=TokenUsage(prompt_tokens=5, completion_tokens=0),
            started_at=0.0,
            first_chunk_at=0.1,
            finished_at=1.0,
        )

    assert metric.prompt_tokens == 5
    assert metric.completion_tokens == 0
    assert metric.tokens_per_sec is None


def test_build_response_metric_handles_missing_usage_and_first_chunk():
    with _patched_memory():
        metric = build_response_metric(
            model_id="some/model",
            backend_name="gguf",
            usage=None,
            started_at=0.0,
            first_chunk_at=None,
            finished_at=0.5,
        )

    assert metric.prompt_tokens is None
    assert metric.completion_tokens is None
    assert metric.tokens_per_sec is None
    assert metric.ttft_ms is None
    assert metric.latency_ms == 500.0


def test_turn_recorder_collects_text_terminal_metadata_and_last_error():
    recorder = TurnRecorder()
    usage = TokenUsage(prompt_tokens=3, completion_tokens=2)

    recorder.observe(ChatChunk(delta=""))
    assert recorder.first_chunk_at is None  # an empty delta is not a first token
    recorder.observe(ChatChunk(delta="Hel"))
    recorder.observe(ChatChunk(delta="lo"))
    recorder.observe(
        ChatChunk(done=True, usage=usage, tools_called=["calculator"], retries=1)
    )

    assert recorder.text == "Hello"
    assert recorder.first_chunk_at is not None
    assert (recorder.usage, recorder.tools_called, recorder.retries) == (
        usage,
        ["calculator"],
        1,
    )
    assert recorder.error is None

    recorder.observe(ChatChunk(delta="ignored", done=True, error="boom"))
    assert recorder.error == "boom"
    assert recorder.text == "Hello"  # an error chunk's delta is never part of the reply
