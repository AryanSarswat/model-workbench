import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app
from app.models import DownloadedModelRecord

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _override_get_session():
    with Session(_test_engine) as session:
        yield session


app.dependency_overrides[get_session] = _override_get_session
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_db():
    SQLModel.metadata.create_all(_test_engine)
    yield
    SQLModel.metadata.drop_all(_test_engine)


def _seed(**overrides) -> int:
    defaults = {
        "repo_id": "meta-llama/Llama-3-8B",
        "backend": "gguf",
        "quant": "model.Q4_K_M.gguf",
        "local_path": "/tmp/does-not-matter",
        "size_bytes": 1024,
    }
    with Session(_test_engine) as session:
        record = DownloadedModelRecord(**{**defaults, **overrides})
        session.add(record)
        session.commit()
        session.refresh(record)
        return record.id


def test_list_downloaded_returns_seeded_records():
    _seed()
    response = client.get("/models/downloaded")
    assert response.status_code == 200
    [record] = response.json()
    assert record["repo_id"] == "meta-llama/Llama-3-8B"


def test_list_downloaded_empty_when_nothing_seeded():
    response = client.get("/models/downloaded")
    assert response.status_code == 200
    assert response.json() == []


def test_delete_downloaded_removes_db_record_and_file(tmp_path):
    real_file = tmp_path / "model.gguf"
    real_file.write_bytes(b"fake weights")
    record_id = _seed(local_path=str(real_file))

    response = client.delete(f"/models/downloaded/{record_id}")

    assert response.status_code == 204
    assert not real_file.exists()
    assert client.get("/models/downloaded").json() == []


def test_delete_downloaded_removes_directory(tmp_path):
    real_dir = tmp_path / "snapshot"
    real_dir.mkdir()
    (real_dir / "config.json").write_text("{}")
    record_id = _seed(backend="transformers", quant=None, local_path=str(real_dir))

    response = client.delete(f"/models/downloaded/{record_id}")

    assert response.status_code == 204
    assert not real_dir.exists()


def test_delete_missing_record_returns_404():
    response = client.delete("/models/downloaded/9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "download_not_found"


def test_downloaded_route_is_not_swallowed_by_discovery_catch_all():
    """discovery_router's /{model_id:path} matches ANY string under /models/, including
    "downloaded" -- downloads_router must be registered first in main.py or this 404s."""
    response = client.get("/models/downloaded")
    assert response.status_code == 200


def test_delete_is_safe_when_file_already_gone(tmp_path):
    """The DB record can outlive the file (e.g. manually deleted outside the app) --
    deleting should still succeed and clean up the record."""
    missing_path = tmp_path / "already-gone.gguf"
    record_id = _seed(local_path=str(missing_path))

    response = client.delete(f"/models/downloaded/{record_id}")

    assert response.status_code == 204
