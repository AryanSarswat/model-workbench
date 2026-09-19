"""Local transformers inference from a downloaded snapshot -- fallback for models
without a GGUF build (MPS/CUDA/CPU auto-detected).

Same lifecycle shape as LlamaCppBackend: the snapshot stays loaded in a process-wide
cache (reloading weights every turn would be multi-GB per request), so aclose() is a
no-op for Protocol conformance. Single-user tool, so no eviction -- the most recently
used snapshot simply stays resident.

Generation runs until the model's EOS token -- no token cap. trust_remote_code stays
off: a snapshot is an arbitrary user-chosen repo, and loading it must never execute
repo-shipped code; models that need custom code surface a terminal load error instead.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage

_CACHE: dict[str, tuple[AutoModelForCausalLM, AutoTokenizer]] = {}
_CACHE_LOCK = threading.Lock()
_SENTINEL = object()


def _detect_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class TransformersBackend:
    def __init__(self, snapshot_dir: str | Path) -> None:
        self._snapshot_dir = str(snapshot_dir)
        self._device = _detect_device()

    def capabilities(self) -> BackendCapabilities:
        # outlines guided decoding + native chat-template tool calling (both wired up
        # once structured output / tool calling land).
        return BackendCapabilities(structured_output_mode="guided", native_tool_calling=True)

    def _get_model(self) -> tuple[AutoModelForCausalLM, AutoTokenizer]:
        with _CACHE_LOCK:
            cached = _CACHE.get(self._snapshot_dir)
            if cached is None:
                tokenizer = AutoTokenizer.from_pretrained(self._snapshot_dir)
                model = AutoModelForCausalLM.from_pretrained(
                    self._snapshot_dir,
                    torch_dtype=torch.float16 if self._device != "cpu" else torch.float32,
                    trust_remote_code=False,
                ).to(self._device)
                model.eval()
                cached = (model, tokenizer)
                _CACHE[self._snapshot_dir] = cached
            return cached

    async def aclose(self) -> None:
        """No-op -- the cached model stays loaded for the next turn. The chat router
        still calls this (it closes whatever backend get_backend() returned), so the
        method exists for Protocol conformance, not because there's anything to free."""

    async def stream_chat(
        self, model_id: str, messages: list[ChatMessage]
    ) -> AsyncIterator[ChatChunk]:
        # model_id is Protocol compat only -- the registry already bound this backend
        # to a specific snapshot dir, so there's nothing left to resolve per request.
        try:
            model, tokenizer = await asyncio.to_thread(self._get_model)
        except Exception as e:  # noqa: BLE001 -- any load failure becomes a terminal
            # error chunk, never a mid-stream traceback (same contract as other backends)
            yield ChatChunk(done=True, error=f"failed to load {self._snapshot_dir}: {e}")
            return
        try:
            inputs = tokenizer.apply_chat_template(
                [m.model_dump() for m in messages],
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            ).to(self._device)
            streamer = TextIteratorStreamer(tokenizer, skip_prompt=True)
            # generate() runs on a worker thread while this coroutine drains the
            # streamer. A generate crash must still terminate the stream (never hang
            # the SSE connection), so the wrapper always signals the streamer end and
            # the original error is reported after the drain.
            errors: list[Exception] = []

            def _generate() -> None:
                try:
                    model.generate(**inputs, streamer=streamer)
                except Exception as e:  # noqa: BLE001 -- captured, reported below
                    errors.append(e)
                finally:
                    streamer.end()

            thread = threading.Thread(target=_generate, daemon=True)
            thread.start()
            while True:
                text = await asyncio.to_thread(next, streamer, _SENTINEL)
                if text is _SENTINEL:
                    break
                if text:
                    yield ChatChunk(delta=text)
            await asyncio.to_thread(thread.join)
            if errors:
                yield ChatChunk(done=True, error=str(errors[0]))
            else:
                yield ChatChunk(done=True)
        except Exception as e:  # noqa: BLE001 -- see above
            yield ChatChunk(done=True, error=str(e))
