from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from huggingface_hub.errors import HTTPError, RepositoryNotFoundError

from app.discovery.hf_client import get_model_detail, get_snapshot_files
from app.discovery.schemas import ModelDetail
from app.errors import WorkbenchError
from app.main import app
from tests.test_discovery import _fake_model

client = TestClient(app)


def _sibling(rfilename: str, size: int | None = 1024):
    return SimpleNamespace(rfilename=rfilename, size=size)


def _fake_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("GET", "https://huggingface.co"))


def test_get_model_detail_filters_to_gguf_files_only():
    model = _fake_model(
        siblings=[
            _sibling("model.gguf", size=4096),
            _sibling("README.md"),
            _sibling("config.json"),
        ]
    )
    with patch("app.discovery.hf_client.model_info", return_value=model):
        detail = get_model_detail("meta-llama/Llama-3-8B")
    assert [f.filename for f in detail.gguf_files] == ["model.gguf"]
    assert detail.gguf_files[0].size_bytes == 4096


def test_get_model_detail_maps_common_fields():
    model = _fake_model(siblings=[])
    with patch("app.discovery.hf_client.model_info", return_value=model):
        detail = get_model_detail("meta-llama/Llama-3-8B")
    assert detail.id == "meta-llama/Llama-3-8B"
    assert detail.downloads == 12345


def test_get_model_detail_reports_dominant_dtype_by_parameter_count():
    safetensors = SimpleNamespace(parameters={"F32": 1_000, "BF16": 7_000_000_000}, total=7_001_000)
    model = _fake_model(siblings=[], safetensors=safetensors)
    with patch("app.discovery.hf_client.model_info", return_value=model):
        detail = get_model_detail("meta-llama/Llama-3-8B")
    assert detail.parameter_count == 7_001_000
    assert detail.dtype == "BF16"


def test_get_model_detail_leaves_parameter_info_none_without_safetensors():
    model = _fake_model(siblings=[])  # safetensors defaults to None in _fake_model
    with patch("app.discovery.hf_client.model_info", return_value=model):
        detail = get_model_detail("meta-llama/Llama-3-8B")
    assert detail.parameter_count is None
    assert detail.dtype is None


def test_get_snapshot_files_excludes_gguf_and_keeps_the_rest():
    model = _fake_model(
        siblings=[
            _sibling("model.gguf", size=4096),
            _sibling("config.json", size=100),
            _sibling("tokenizer.json", size=None),
        ]
    )
    with patch("app.discovery.hf_client.model_info", return_value=model):
        files = get_snapshot_files("org/model")

    assert [(f.filename, f.size_bytes) for f in files] == [
        ("config.json", 100),
        ("tokenizer.json", None),
    ]


def test_get_model_detail_raises_404_for_missing_repo():
    not_found = RepositoryNotFoundError("nope", response=_fake_response(404))
    with (
        patch("app.discovery.hf_client.model_info", side_effect=not_found),
        pytest.raises(WorkbenchError) as exc_info,
    ):
        get_model_detail("nonexistent/model")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "model_not_found"


def test_get_model_detail_raises_502_for_hub_http_error():
    with (
        patch("app.discovery.hf_client.model_info", side_effect=HTTPError("boom")),
        pytest.raises(WorkbenchError) as exc_info,
    ):
        get_model_detail("meta-llama/Llama-3-8B")
    assert exc_info.value.status_code == 502


def test_model_detail_endpoint_returns_mapped_result():
    with patch("app.discovery.router.get_model_detail") as mock_detail:
        mock_detail.return_value = ModelDetail(id="meta-llama/Llama-3-8B", gguf_files=[])
        response = client.get("/models/meta-llama/Llama-3-8B")
    assert response.status_code == 200
    assert response.json()["id"] == "meta-llama/Llama-3-8B"


def test_discover_route_is_not_swallowed_by_model_detail_catch_all():
    """/models/{model_id:path} is registered after /models/discover -- this locks in that
    the static route still wins, since both could otherwise match "discover" as a model id."""
    with (
        patch("app.discovery.router.list_discoverable_models", return_value=[]) as mock_list,
        patch("app.discovery.router.get_model_detail") as mock_detail,
    ):
        response = client.get("/models/discover")
    assert response.status_code == 200
    mock_list.assert_called_once()
    mock_detail.assert_not_called()


@pytest.mark.network
def test_model_detail_endpoint_against_real_hf_hub():
    response = client.get("/models/TheBloke/Llama-2-7B-GGUF")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "TheBloke/Llama-2-7B-GGUF"
    assert len(body["gguf_files"]) > 0
    assert all(f["filename"].endswith(".gguf") for f in body["gguf_files"])
