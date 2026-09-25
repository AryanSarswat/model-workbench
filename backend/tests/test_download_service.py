from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.downloads import service
from app.models import DownloadedModelRecord, DownloadJob

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@pytest.fixture(autouse=True)
def _use_test_db(tmp_path, monkeypatch):
    """Points the service at the in-memory DB and a throwaway models dir. Tests take
    `tmp_path` too -- pytest hands them the same directory this fixture installed."""
    monkeypatch.setattr(service, "engine", _test_engine)
    monkeypatch.setattr(service, "MODELS_DIR", tmp_path)
    SQLModel.metadata.create_all(_test_engine)
    yield
    SQLModel.metadata.drop_all(_test_engine)


def _seed_job(**overrides) -> int:
    defaults = {"repo_id": "meta-llama/Llama-3-8B", "filename": "model.Q4_K_M.gguf"}
    with Session(_test_engine) as session:
        job = DownloadJob(**{**defaults, **overrides})
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id


@contextmanager
def _fake_stream(body: bytes, content_length: str | None):
    """Stands in for httpx.stream("GET", ...), yielding a response over `body` in two
    chunks so the percent-tracking logic actually exercises more than one iteration."""

    class _FakeResponse:
        headers = {"content-length": content_length} if content_length else {}

        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self, chunk_size: int):
            mid = len(body) // 2
            yield body[:mid]
            yield body[mid:]

    yield _FakeResponse()


def test_run_download_success(tmp_path):
    job_id = _seed_job()
    content = b"fake gguf weights"

    with (
        patch("app.downloads.service.hf_hub_url", return_value="https://example.com/model.gguf"),
        patch(
            "httpx.stream",
            return_value=_fake_stream(content, content_length=str(len(content))),
        ),
    ):
        service.run_download(job_id, "meta-llama/Llama-3-8B", "model.Q4_K_M.gguf")

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "completed"
        assert job.percent == 100.0
        assert job.downloaded_model_id is not None

        record = session.get(DownloadedModelRecord, job.downloaded_model_id)
        assert record.repo_id == "meta-llama/Llama-3-8B"
        assert record.size_bytes == len(content)

    dest_file = tmp_path / "meta-llama/Llama-3-8B" / "model.Q4_K_M.gguf"
    assert dest_file.read_bytes() == content


def test_run_download_http_error_marks_job_failed(tmp_path):
    job_id = _seed_job()

    @contextmanager
    def _raising_stream(*args, **kwargs):
        raise httpx.ConnectError("connection refused")
        yield  # pragma: no cover -- unreachable, makes this a generator for @contextmanager

    with (
        patch("app.downloads.service.hf_hub_url", return_value="https://example.com/model.gguf"),
        patch("httpx.stream", _raising_stream),
    ):
        service.run_download(job_id, "meta-llama/Llama-3-8B", "model.Q4_K_M.gguf")

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "connection refused" in job.error
        assert session.exec(select(DownloadedModelRecord)).first() is None

    assert not (tmp_path / "meta-llama/Llama-3-8B" / "model.Q4_K_M.gguf").exists()


def test_run_download_truncated_stream_marks_job_failed(tmp_path):
    """A dropped connection mid-body doesn't raise -- iter_bytes just stops yielding.
    Without a downloaded-vs-declared-length check, a short file would be recorded as a
    completed download."""
    job_id = _seed_job()
    content = b"fake gguf weights"

    with (
        patch("app.downloads.service.hf_hub_url", return_value="https://example.com/model.gguf"),
        patch(
            "httpx.stream",
            # Declares more bytes than the body actually contains.
            return_value=_fake_stream(content, content_length=str(len(content) + 100)),
        ),
    ):
        service.run_download(job_id, "meta-llama/Llama-3-8B", "model.Q4_K_M.gguf")

    with Session(_test_engine) as session:
        job = session.get(DownloadJob, job_id)
        assert job.status == "failed"
        assert "stream ended early" in job.error
        assert session.exec(select(DownloadedModelRecord)).first() is None

    assert not (tmp_path / "meta-llama/Llama-3-8B" / "model.Q4_K_M.gguf").exists()


def test_run_download_unwritable_dest_marks_job_failed(tmp_path):
    """A mkdir failure (here: a file where the repo dir should be) must fail the job,
    not escape the background task and leave the job stuck at "downloading"."""
    (tmp_path / "meta-llama").write_text("not a directory")
    job_id = _seed_job()

    service.run_download(job_id, "meta-llama/Llama-3-8B", "model.Q4_K_M.gguf")

    with Session(_test_engine) as session:
        assert session.get(DownloadJob, job_id).status == "failed"
