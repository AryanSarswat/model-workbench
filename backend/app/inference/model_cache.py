"""In-memory model cache shared by the local backends (llama.cpp, transformers).

Each backend keeps at most ONE loaded model: loading a different path drops the
previous one, so switching models in the Playground or across an eval run doesn't
accumulate weights until RAM/VRAM runs out. The model is freed by dropping the
cache's reference -- never closed explicitly, since a request already streaming
from it still holds its own reference and must be able to finish.

No heavy imports here, so the downloads router can evict on delete without loading
llama.cpp or torch.
"""

from __future__ import annotations

import gc
import threading
import weakref
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")

_caches: weakref.WeakSet[LoadedModelCache] = weakref.WeakSet()


class LoadedModelCache(Generic[T]):
    def __init__(self, on_evict: Callable[[T], None] | None = None) -> None:
        """on_evict runs after a model is dropped (e.g. to release accelerator memory)."""
        self._on_evict = on_evict
        self._lock = threading.Lock()
        self._path: str | None = None
        self._model: T | None = None
        _caches.add(self)

    def get_or_load(self, path: str, load: Callable[[], T]) -> T:
        with self._lock:
            if self._path != path:
                self._drop()
                self._model = load()
                self._path = path
            return self._model  # type: ignore[return-value]

    def get(self, path: str) -> T | None:
        with self._lock:
            return self._model if self._path == path else None

    def evict(self, path: str | None = None) -> None:
        """Drop the loaded model -- only if it is `path`, when given."""
        with self._lock:
            if path is None or self._path == path:
                self._drop()

    def _drop(self) -> None:
        model, self._model, self._path = self._model, None, None
        if model is None:
            return
        if self._on_evict is not None:
            self._on_evict(model)
        del model
        gc.collect()


def evict_path(path: str) -> None:
    """Unload `path` from whichever local backend has it loaded."""
    for cache in list(_caches):
        cache.evict(path)
