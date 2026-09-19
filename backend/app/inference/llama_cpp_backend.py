"""Local GGUF inference via llama-cpp-python -- runs on any hardware (CPU fallback).

The model file stays loaded in a process-wide cache: constructing a fresh Llama per
chat turn would reload multi-GB weights every request, so unlike HFInferenceAPIBackend
(which must be closed per request to release its httpx pool) this backend's aclose()
is a no-op and the instance is reused. Single-user tool, so no eviction -- the most
recently used model simply stays resident.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path

from llama_cpp import Llama

from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage

_CACHE: dict[str, Llama] = {}
_CACHE_LOCK = threading.Lock()
_SENTINEL = object()


class LlamaCppBackend:
    def __init__(self, model_path: str | Path) -> None:
        self._model_path = str(model_path)

    def capabilities(self) -> BackendCapabilities:
        # JSON Schema constrains decoding via GBNF grammar (wired up once structured
        # output lands); chat-template tool calling is natively supported.
        return BackendCapabilities(structured_output_mode="grammar", native_tool_calling=True)

    def _get_llama(self) -> Llama:
        with _CACHE_LOCK:
            llama = _CACHE.get(self._model_path)
            if llama is None:
                llama = Llama(model_path=self._model_path, verbose=False)
                _CACHE[self._model_path] = llama
            return llama

    async def aclose(self) -> None:
        """No-op -- the cached Llama stays loaded for the next turn. The chat router
        still calls this (it closes whatever backend get_backend() returned), so the
        method exists for Protocol conformance, not because there's anything to free."""

    async def stream_chat(
        self, model_id: str, messages: list[ChatMessage]
    ) -> AsyncIterator[ChatChunk]:
        # model_id is Protocol compat only -- the registry already bound this backend
        # to a specific local file, so there's nothing left to resolve per request.
        try:
            llama = await asyncio.to_thread(self._get_llama)
        except Exception as e:  # noqa: BLE001 -- any load failure becomes a terminal
            # error chunk, never a mid-stream traceback (same contract as HF backend)
            yield ChatChunk(done=True, error=f"failed to load {self._model_path}: {e}")
            return
        try:
            stream = llama.create_chat_completion(
                messages=[m.model_dump() for m in messages],
                stream=True,
            )
            while True:
                chunk = await asyncio.to_thread(next, stream, _SENTINEL)
                if chunk is _SENTINEL:
                    break
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield ChatChunk(delta=delta)
            yield ChatChunk(done=True)
        except Exception as e:  # noqa: BLE001 -- see above
            yield ChatChunk(done=True, error=str(e))
