from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.discovery.schemas import SnapshotFile
from app.downloads import service
from app.models import DownloadedModelRecord, DownloadJob

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@pytest.fixture(autouse=True)
def _use_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "engine", _test_engine)
    monkeypatch.setattr(service, "MODELS_DIR", tmp_path)
    SQLModel.metadata.create_all(_test_engine)
    yield
    SQLModel.metadata.drop_all(_test_engine)


def _seed_job() -> int:
    with Session(_test_engine) as session:
        job = DownloadJob(repo_id="org/model", filename="")
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id


def _streams(bodies: dict[str, bytes]):
    """httpx.stream replacement serving a fixed body per filename-suffixed URL."""

    @contextmanager
    def _response(body: bytes):
        class _FakeResponse:
            def __init__(self) -> None:
                self.headers = {"content-length": str(len(body))}

            def raise_for_status(self) -> None:
                pass

            def iter_bytes(self, chunk_size: int):
                mid = len(body) // 2
                yield body[:mid]
                yield body[mid:]

        yield _FakeResponse()

    def _factory(method: str, url: str, **kwargs):
        for filename, body in bodies.items():
            if url.endswith(filename):
                return _response(body)
        raise AssertionError(f"unexpected download URL: {url}")

    return _factory


def _hub_url(repo_id: str, filename: str) -> str:
    return f"https://example.com/{filename}"


def test_run_snapshot_download_success_with_aggregated_progress(tmp_path, monkeypatch):
    job_id = _seed_job()
    files = [
        SnapshotFile(filename="config.json", size_bytes=100),
        SnapshotFile(filename="data/vocab.txt", size_bytes=300),
    ]
    seen_percents = []
    real_save = service._save

    def _recording_save(session: Session, job: DownloadJob) -> None:
        seen_percents.append(job.percent)
        real_save(session, job)

    monkeypatch.setattr(service, "_save", _recording_save)

    with (
        patch("app.downloads.service.hf_hub_url", side_effect=_hub_url),
        patch("httpx.stream", side_effect=_streams({"config.json": b"a" * 100, "data/vocab.txt": b"b" * 300})),
    ):
        service.run_snapshot_download(job_id, "org/model", files)

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "completed"
        assert job.percent == 100.0
        assert job.filename == "data/vocab.txt"
        assert job.downloaded_model_id is not None

        record = session.get(DownloadedModelRecord, job.downloaded_model_id)
        assert record.backend == "transformers"
        assert record.quant is None
        assert record.size_bytes == 400
        assert record.local_path.endswith("snapshot")

    snapshot_dir = tmp_path / "org/model" / "snapshot"
    assert (snapshot_dir / "config.json").read_bytes() == b"a" * 100
    assert (snapshot_dir / "data" / "vocab.txt").read_bytes() == b"b" * 300

    # 25% after the first file proves aggregation across files -- per-file percent
    # would read 100% there. 100% appears only on real completion.
    assert 25.0 in seen_percents
    assert max(seen_percents[:-1]) <= 99.0
    assert seen_percents[-1] == 100.0


def test_run_snapshot_download_failure_removes_only_the_snapshot_dir(tmp_path):
    job_id = _seed_job()
    files = [
        SnapshotFile(filename="config.json", size_bytes=100),
        SnapshotFile(filename="model.safetensors", size_bytes=300),
    ]
    # A GGUF of the same repo downloaded earlier lives next to the snapshot dir.
    gguf_file = tmp_path / "org/model" / "model.gguf"
    gguf_file.parent.mkdir(parents=True, exist_ok=True)
    gguf_file.write_bytes(b"gguf weights")

    def _failing_stream(method: str, url: str, **kwargs):
        if url.endswith("model.safetensors"):
            raise httpx.ConnectError("connection refused")
        return _streams({"config.json": b"a" * 100})(method, url, **kwargs)

    with (
        patch("app.downloads.service.hf_hub_url", side_effect=_hub_url),
        patch("httpx.stream", side_effect=_failing_stream),
    ):
        service.run_snapshot_download(job_id, "org/model", files)

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "connection refused" in job.error
        assert session.exec(select(DownloadedModelRecord)).first() is None

    assert not (tmp_path / "org/model" / "snapshot").exists()
    assert gguf_file.read_bytes() == b"gguf weights"


def test_run_snapshot_download_with_no_files_fails_loudly():
    job_id = _seed_job()

    service.run_snapshot_download(job_id, "org/model", [])

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "No transformers snapshot files" in job.error
        assert session.exec(select(DownloadedModelRecord)).first() is None


def test_run_snapshot_download_truncated_file_marks_job_failed(tmp_path):
    """Like the single-file case: a dropped connection mid-body just stops yielding,
    so each snapshot file's written-vs-declared length is checked too."""
    job_id = _seed_job()
    files = [SnapshotFile(filename="config.json", size_bytes=200)]

    @contextmanager
    def _short_stream(method: str, url: str, **kwargs):
        class _FakeResponse:
            def __init__(self) -> None:
                # Declares 200 bytes but only serves 100.
                self.headers = {"content-length": "200"}

            def raise_for_status(self) -> None:
                pass

            def iter_bytes(self, chunk_size: int):
                yield b"a" * 100

        yield _FakeResponse()

    with (
        patch("app.downloads.service.hf_hub_url", side_effect=_hub_url),
        patch("httpx.stream", side_effect=_short_stream),
    ):
        service.run_snapshot_download(job_id, "org/model", files)

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "stream ended early" in job.error
        assert session.exec(select(DownloadedModelRecord)).first() is None

    assert not (tmp_path / "org/model" / "snapshot").exists()
