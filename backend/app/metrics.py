"""Turns one chat turn's timing/usage into a response_metrics row. Shared by
POST /chat/stream and the eval engine so the TTFT/tokens-per-sec math lives in one
place.
"""

from __future__ import annotations

import time

from app.config import get_memory_usage
from app.inference.schemas import ChatChunk, TokenUsage
from app.models import ResponseMetricRecord


def build_response_metric(
    model_id: str,
    backend_name: str,
    usage: TokenUsage | None,
    started_at: float,
    first_chunk_at: float | None,
    finished_at: float,
) -> ResponseMetricRecord:
    """Timestamps are time.monotonic() readings, started_at <= first_chunk_at <=
    finished_at (not validated). first_chunk_at is None when no non-empty delta
    arrived, leaving ttft_ms None. The caller adds the record to its session.
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


class TurnRecorder:
    """Collects one stream_chat() turn as it is consumed: reply text, TTFT, the
    terminal chunk's metadata, and the last error."""

    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self.first_chunk_at: float | None = None
        self.parts: list[str] = []
        self.error: str | None = None
        self.usage: TokenUsage | None = None
        self.tools_called: list[str] = []
        self.retries = 0

    def observe(self, chunk: ChatChunk) -> None:
        if chunk.error is not None:
            self.error = chunk.error
        elif chunk.delta:
            if self.first_chunk_at is None:
                self.first_chunk_at = time.monotonic()
            self.parts.append(chunk.delta)
        if chunk.done:
            self.usage = chunk.usage
            self.tools_called = chunk.tools_called
            self.retries = chunk.retries

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def build_metric(self, model_id: str, backend_name: str) -> ResponseMetricRecord:
        """The turn's metric, finished as of now."""
        return build_response_metric(
            model_id=model_id,
            backend_name=backend_name,
            usage=self.usage,
            started_at=self.started_at,
            first_chunk_at=self.first_chunk_at,
            finished_at=time.monotonic(),
        )
