from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.discovery.schemas import GgufFile, ModelDetail
from app.main import app
from app.models import DownloadedModelRecord, DownloadJob

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


def _detail(**overrides) -> ModelDetail:
    defaults = {
        "id": "meta-llama/Llama-3-8B",
        "gguf_files": [GgufFile(filename="model.Q4_K_M.gguf", size_bytes=1024)],
    }
    return ModelDetail(**{**defaults, **overrides})


def test_start_download_creates_job_and_schedules_background_task():
    scheduled = {}

    def _fake_run_download(job_id: int, repo_id: str, filename: str) -> None:
        scheduled["args"] = (job_id, repo_id, filename)

    with (
        patch("app.downloads.router.get_model_detail", return_value=_detail()),
        patch("app.downloads.router.run_download", _fake_run_download),
    ):
        response = client.post(
            "/models/meta-llama/Llama-3-8B/download",
            json={"filename": "model.Q4_K_M.gguf"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert scheduled["args"] == (body["id"], "meta-llama/Llama-3-8B", "model.Q4_K_M.gguf")


def test_start_download_rejects_filename_not_in_repo():
    with patch("app.downloads.router.get_model_detail", return_value=_detail()):
        response = client.post(
            "/models/meta-llama/Llama-3-8B/download",
            json={"filename": "does-not-exist.gguf"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_gguf_filename"


def test_get_download_job_returns_seeded_job():
    with Session(_test_engine) as session:
        job = DownloadJob(
            repo_id="meta-llama/Llama-3-8B",
            filename="model.Q4_K_M.gguf",
            status="downloading",
            percent=42.0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    response = client.get(f"/models/downloads/{job_id}")

    assert response.status_code == 200
    assert response.json()["percent"] == 42.0


def test_get_download_job_missing_returns_404():
    response = client.get("/models/downloads/9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "download_job_not_found"
