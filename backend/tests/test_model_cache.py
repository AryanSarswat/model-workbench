"""LoadedModelCache: local backends keep one model in memory, not every model ever used."""

import gc
import weakref

from app.inference.model_cache import LoadedModelCache, evict_path


class _Model:
    pass


def test_loading_a_different_model_releases_the_previous_one():
    evicted: list[int] = []  # ids, so the record itself doesn't keep a model alive
    cache: LoadedModelCache[_Model] = LoadedModelCache(on_evict=lambda m: evicted.append(id(m)))
    first = cache.get_or_load("/models/a.gguf", _Model)
    first_ref = weakref.ref(first)

    assert cache.get_or_load("/models/a.gguf", _Model) is first  # reused, not reloaded
    second = cache.get_or_load("/models/b.gguf", _Model)

    assert evicted == [id(first)]
    del first
    gc.collect()
    assert first_ref() is None  # nothing keeps the old weights alive
    assert cache.get("/models/b.gguf") is second


def test_evict_path_unloads_that_model_from_whichever_backend_holds_it():
    gguf: LoadedModelCache[_Model] = LoadedModelCache()
    snapshots: LoadedModelCache[_Model] = LoadedModelCache()
    gguf.get_or_load("/models/a.gguf", _Model)
    snapshots.get_or_load("/models/b/snapshot", _Model)

    evict_path("/models/a.gguf")

    assert gguf.get("/models/a.gguf") is None
    assert snapshots.get("/models/b/snapshot") is not None
