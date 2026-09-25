from contextlib import contextmanager
from pathlib import Path
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
        job = DownloadJob(repo_id="org/model", kind="snapshot")
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
        patch(
            "httpx.stream",
            side_effect=_streams({"config.json": b"a" * 100, "data/vocab.txt": b"b" * 300}),
        ),
    ):
        service.run_snapshot_download(job_id, "org/model", files)

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "completed"
        assert job.percent == 100.0
        assert job.kind == "snapshot"
        assert job.filename is None
        assert job.current_file == "data/vocab.txt"
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


@pytest.mark.parametrize("filename", ["../evil.txt", "/tmp/abs-evil-snapshot.txt"])
def test_run_snapshot_download_rejects_escaping_paths(tmp_path, filename):
    """Filenames come from Hub metadata -- `..` or absolute paths must fail the job,
    never write outside the snapshot dir."""
    job_id = _seed_job()

    service.run_snapshot_download(job_id, "org/model", [SnapshotFile(filename=filename)])

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "unsafe download path" in job.error
        assert session.exec(select(DownloadedModelRecord)).first() is None

    assert not (tmp_path / "evil.txt").exists()
    assert not Path("/tmp/abs-evil-snapshot.txt").exists()


def test_run_download_rejects_escaping_filename(tmp_path):
    job_id = _seed_job()

    service.run_download(job_id, "org/model", "../evil.gguf")

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "unsafe download path" in job.error

    assert not (tmp_path / "evil.gguf").exists()


def test_run_snapshot_download_rejects_escaping_repo_id(tmp_path):
    job_id = _seed_job()

    service.run_snapshot_download(
        job_id, "../evil", [SnapshotFile(filename="config.json", size_bytes=10)]
    )

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "unsafe download path" in job.error

    assert not (tmp_path / "evil").exists()


def test_run_snapshot_download_unwritable_dest_marks_job_failed(tmp_path):
    (tmp_path / "org").write_text("not a directory")
    job_id = _seed_job()

    service.run_snapshot_download(job_id, "org/model", [SnapshotFile(filename="config.json")])

    with Session(_test_engine) as session:
        assert session.get(DownloadJob, job_id).status == "failed"


def test_safe_dest_allows_normal_nested_paths(tmp_path):
    assert service._safe_dest(tmp_path, "org/model", "data/vocab.txt") == (
        tmp_path / "org/model" / "data" / "vocab.txt"
    )


def test_safe_dest_rejects_symlink_escape(tmp_path):
    base = tmp_path / "models"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "sub").symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError, match="unsafe download path"):
        service._safe_dest(base, "sub", "f.txt")


def test_run_snapshot_download_with_unknown_sizes_clamps_and_completes(tmp_path, monkeypatch):
    """No Hub sizes at all: percent sits at 0 (never a stuck 99 from overshoot, never
    100 early), detail still names the current file, and the job completes at 100."""
    job_id = _seed_job()
    files = [SnapshotFile(filename="a.bin"), SnapshotFile(filename="b.bin")]
    seen = []
    real_save = service._save

    def _recording_save(session: Session, job: DownloadJob) -> None:
        seen.append((job.percent, job.detail))
        real_save(session, job)

    monkeypatch.setattr(service, "_save", _recording_save)

    with (
        patch("app.downloads.service.hf_hub_url", side_effect=_hub_url),
        patch("httpx.stream", side_effect=_streams({"a.bin": b"a" * 100, "b.bin": b"b" * 300})),
    ):
        service.run_snapshot_download(job_id, "org/model", files)

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "completed"
        assert job.percent == 100.0
        assert session.get(DownloadedModelRecord, job.downloaded_model_id).size_bytes == 400

    assert all(percent <= 99.0 for percent, _ in seen[:-1])
    assert any("unknown total" in detail for _, detail in seen)
    assert any("file 2/2" in detail for _, detail in seen)
