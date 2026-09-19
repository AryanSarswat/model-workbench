"""Thin wrapper around huggingface_hub's model listing, isolating the third-party API so the
rest of the app depends on our own DiscoveredModel shape instead of ModelInfo directly.
"""

from __future__ import annotations

from typing import Any, Literal

from huggingface_hub import list_models, model_info
from huggingface_hub.errors import HTTPError, RepositoryNotFoundError

from app.discovery.schemas import DiscoveredModel, GgufFile, ModelDetail, SnapshotFile
from app.errors import WorkbenchError

_SORT_BY: dict[str, str] = {
    "trending": "trending_score",
    "recent": "created_at",
}


def _common_fields(model: Any) -> dict[str, Any]:
    """Fields shared by the list view (ModelInfo without files_metadata) and the detail
    view (ModelInfo with files_metadata) -- everything DiscoveredModel declares."""
    return {
        "id": model.id,
        "author": model.author,
        "pipeline_tag": model.pipeline_tag,
        "downloads": model.downloads,
        "likes": model.likes,
        "trending_score": getattr(model, "trending_score", None),
        "created_at": model.created_at,
        "gated": model.gated,
        "tags": model.tags or [],
        "library_name": model.library_name,
    }


def _parameter_info(model: Any) -> tuple[int | None, str | None]:
    """(parameter_count, dominant dtype) from safetensors metadata, when available.

    Only populated by model_info(files_metadata=True) -- None for the list view. A model
    can mix dtypes across shards; we report the one with the most parameters, since that's
    what dominates the memory estimate the feasibility check will use this for.
    """
    safetensors = getattr(model, "safetensors", None)
    if safetensors is None or not safetensors.parameters:
        return None, None
    dominant_dtype = max(safetensors.parameters, key=safetensors.parameters.get)
    return safetensors.total, dominant_dtype


def list_discoverable_models(
    sort: Literal["trending", "recent"], limit: int = 20
) -> list[DiscoveredModel]:
    """Text-generation models from the HF Hub, sorted by trending score or recency."""
    try:
        results = list_models(
            pipeline_tag="text-generation",
            sort=_SORT_BY[sort],
            limit=limit,
        )
        return [DiscoveredModel(**_common_fields(model)) for model in results]
    except HTTPError as e:
        raise WorkbenchError(
            status_code=502,
            code="hf_hub_unreachable",
            message="Could not reach the Hugging Face Hub to list models.",
            details={"original_error": str(e)},
        ) from e


def get_model_detail(model_id: str) -> ModelDetail:
    """Model detail including any GGUF files available in the repo, for the download step
    to offer as a local-run option."""
    model = _fetch_model_info(model_id)

    gguf_files = [
        GgufFile(filename=sibling.rfilename, size_bytes=sibling.size)
        for sibling in model.siblings or []
        if sibling.rfilename.lower().endswith(".gguf") and sibling.size is not None
    ]
    parameter_count, dtype = _parameter_info(model)
    return ModelDetail(
        **_common_fields(model),
        gguf_files=gguf_files,
        parameter_count=parameter_count,
        dtype=dtype,
    )


def get_snapshot_files(model_id: str) -> list[SnapshotFile]:
    """Every non-GGUF file in the repo -- the transformers snapshot. GGUF has its own
    single-file download flow, so it's excluded here rather than downloaded twice."""
    model = _fetch_model_info(model_id)
    return [
        SnapshotFile(filename=sibling.rfilename, size_bytes=sibling.size)
        for sibling in model.siblings or []
        if not sibling.rfilename.lower().endswith(".gguf")
    ]


def _fetch_model_info(model_id: str) -> Any:
    """model_info with files_metadata, mapping Hub errors to WorkbenchErrors -- shared
    by the detail view and the snapshot file listing so the mapping lives in one place."""
    try:
        return model_info(model_id, files_metadata=True)
    except RepositoryNotFoundError as e:
        raise WorkbenchError(
            status_code=404,
            code="model_not_found",
            message=f"No model found on the Hugging Face Hub with id '{model_id}'.",
        ) from e
    except HTTPError as e:
        raise WorkbenchError(
            status_code=502,
            code="hf_hub_unreachable",
            message="Could not reach the Hugging Face Hub to fetch model details.",
            details={"original_error": str(e)},
        ) from e
