from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from huggingface_hub.errors import HTTPError

from app.discovery.hf_client import list_discoverable_models
from app.errors import WorkbenchError
from app.main import app

client = TestClient(app)


def _fake_model(**overrides):
    defaults = {
        "id": "meta-llama/Llama-3-8B",
        "author": "meta-llama",
        "pipeline_tag": "text-generation",
        "downloads": 12345,
        "likes": 678,
        "trending_score": 91.2,
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "gated": False,
        "tags": ["text-generation", "conversational"],
        "library_name": "transformers",
        "safetensors": None,
    }
    return SimpleNamespace(**{**defaults, **overrides})


def test_trending_sort_maps_to_trending_score():
    with patch("app.discovery.hf_client.list_models", return_value=[_fake_model()]) as mock_list:
        list_discoverable_models(sort="trending", limit=10)
    assert mock_list.call_args.kwargs["sort"] == "trending_score"


def test_recent_sort_maps_to_created_at():
    with patch("app.discovery.hf_client.list_models", return_value=[_fake_model()]) as mock_list:
        list_discoverable_models(sort="recent", limit=10)
    assert mock_list.call_args.kwargs["sort"] == "created_at"


def test_maps_hub_fields_onto_discovered_model():
    with patch("app.discovery.hf_client.list_models", return_value=[_fake_model()]):
        [result] = list_discoverable_models(sort="trending")
    assert result.id == "meta-llama/Llama-3-8B"
    assert result.downloads == 12345
    assert result.trending_score == 91.2
    assert result.library_name == "transformers"
    assert result.tags == ["text-generation", "conversational"]


def test_hub_connection_failure_becomes_workbench_error():
    with (
        patch("app.discovery.hf_client.list_models", side_effect=HTTPError("timed out")),
        pytest.raises(WorkbenchError) as exc_info,
    ):
        list_discoverable_models(sort="trending")
    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "hf_hub_unreachable"


def test_discover_endpoint_returns_mapped_results():
    with patch("app.discovery.router.list_discoverable_models", return_value=[]):
        response = client.get("/models/discover?sort=recent&limit=5")
    assert response.status_code == 200
    assert response.json() == []


def test_discover_endpoint_surfaces_hub_error_in_uniform_shape():
    with patch(
        "app.discovery.router.list_discoverable_models",
        side_effect=WorkbenchError(502, "hf_hub_unreachable", "Could not reach the Hub"),
    ):
        response = client.get("/models/discover")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "hf_hub_unreachable"


@pytest.mark.network
def test_discover_endpoint_against_real_hf_hub():
    response = client.get("/models/discover?sort=trending&limit=3")
    assert response.status_code == 200
    assert len(response.json()) <= 3
