"""Thin wrapper around huggingface_hub's model listing, isolating the third-party API so the
rest of the app depends on our own DiscoveredModel shape instead of ModelInfo directly.
"""

from __future__ import annotations

from typing import Literal

from huggingface_hub import list_models
from huggingface_hub.errors import HTTPError

from app.discovery.schemas import DiscoveredModel
from app.errors import WorkbenchError

_SORT_BY: dict[str, str] = {
    "trending": "trending_score",
    "recent": "created_at",
}


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
        return [
            DiscoveredModel(
                id=model.id,
                author=model.author,
                pipeline_tag=model.pipeline_tag,
                downloads=model.downloads,
                likes=model.likes,
                trending_score=getattr(model, "trending_score", None),
                created_at=model.created_at,
                gated=model.gated,
            )
            for model in results
        ]
    except HTTPError as e:
        raise WorkbenchError(
            status_code=502,
            code="hf_hub_unreachable",
            message="Could not reach the Hugging Face Hub to list models.",
            details={"original_error": str(e)},
        ) from e
