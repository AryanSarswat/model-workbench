"""Dataset CRUD tests. The store is pointed at tmp_path via the Settings hook, so the
real data/test_cases/ dir is never touched."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dataset import store as dataset_store
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dataset_store, "get_settings", lambda: Settings(_env_file=None, test_cases_dir=tmp_path)
    )


def _case(case_id="case-001", category="general", **overrides):
    body = {
        "id": case_id,
        "category": category,
        "messages": [{"role": "user", "content": "Say hi."}],
    }
    return {**body, **overrides}


def test_create_and_get_round_trip():
    assert client.post("/dataset/cases", json=_case()).status_code == 201

    response = client.get("/dataset/cases/case-001")

    assert response.status_code == 200
    assert response.json()["id"] == "case-001"
    assert response.json()["messages"] == [{"role": "user", "content": "Say hi."}]


def test_list_filters_by_category():
    client.post("/dataset/cases", json=_case("case-001", "general"))
    client.post("/dataset/cases", json=_case("case-002", "coding"))

    assert {c["id"] for c in client.get("/dataset/cases").json()} == {"case-001", "case-002"}
    filtered = client.get("/dataset/cases", params={"category": "coding"}).json()
    assert [c["id"] for c in filtered] == ["case-002"]
    assert client.get("/dataset/cases", params={"category": "nope"}).json() == []


def test_update_replaces_case():
    client.post("/dataset/cases", json=_case())

    response = client.put("/dataset/cases/case-001", json=_case(tags=["new"]))

    assert response.status_code == 200
    assert response.json()["tags"] == ["new"]
    assert client.get("/dataset/cases/case-001").json()["tags"] == ["new"]


def test_update_id_mismatch_returns_422():
    client.post("/dataset/cases", json=_case())

    response = client.put("/dataset/cases/case-001", json=_case("other-id"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "test_case_id_mismatch"


def test_delete_then_get_returns_404():
    client.post("/dataset/cases", json=_case())

    assert client.delete("/dataset/cases/case-001").status_code == 204

    response = client.get("/dataset/cases/case-001")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "test_case_not_found"


def test_duplicate_id_returns_409():
    client.post("/dataset/cases", json=_case())

    response = client.post("/dataset/cases", json=_case())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "test_case_already_exists"


def test_missing_id_returns_404():
    assert client.get("/dataset/cases/nope").status_code == 404
    assert client.delete("/dataset/cases/nope").status_code == 404
    assert client.put("/dataset/cases/nope", json=_case("nope")).status_code == 404


def test_malformed_body_returns_422():
    assert client.post("/dataset/cases", json={"id": "bad", "category": "general"}).status_code == 422
    assert client.post("/dataset/cases", json=_case("not/url/safe")).status_code == 422
