"""Turns raw chat-turn timing/usage into a persisted response_metrics row.

Both POST /chat/stream (Task 8; every regular chat turn, not just evals -- see
docs/architecture.md's response_metrics design) and the eval engine (Task 15)
will call build_response_metric with whatever they observed collecting a
backend's stream_chat() output, so tokens_per_sec/TTFT math lives in exactly
one place.
"""

from __future__ import annotations

from app.config import get_memory_usage
from app.inference.schemas import TokenUsage
from app.models import ResponseMetricRecord


def build_response_metric(
    model_id: str,
    backend_name: str,
    usage: TokenUsage | None,
    started_at: float,
    first_chunk_at: float | None,
    finished_at: float,
) -> ResponseMetricRecord:
    """started_at/first_chunk_at/finished_at are time.monotonic() readings from
    the caller's own chunk-collection loop. first_chunk_at is None when no
    non-empty delta ever arrived (e.g. an immediate error) -- ttft_ms stays
    None rather than reporting a meaningless "immediate" TTFT. Not yet
    persisted: the caller adds the returned record to its own DB session.

    Callers must ensure started_at <= first_chunk_at <= finished_at (all three
    come from time.monotonic() readings in one collection loop) -- this
    function does not validate ordering, so a misordered call would silently
    produce a negative latency_ms/ttft_ms.
    """
    latency_ms = (finished_at - started_at) * 1000
    ttft_ms = (first_chunk_at - started_at) * 1000 if first_chunk_at is not None else None
    tokens_per_sec = None
    if usage is not None and usage.completion_tokens > 0 and latency_ms > 0:
        tokens_per_sec = usage.completion_tokens / (latency_ms / 1000)
    memory = get_memory_usage()
    return ResponseMetricRecord(
        model_id=model_id,
        backend=backend_name,
        prompt_tokens=usage.prompt_tokens if usage is not None else None,
        completion_tokens=usage.completion_tokens if usage is not None else None,
        tokens_per_sec=tokens_per_sec,
        ttft_ms=ttft_ms,
        latency_ms=latency_ms,
        cost_usd=None,
        ram_used_gb=memory.ram_used_gb,
        vram_used_gb=memory.vram_used_gb,
    )
