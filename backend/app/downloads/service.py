"""Executes model downloads in the background, tracking progress on a DownloadJob row.

Two flows share one httpx streaming core: a single GGUF file, and a transformers
snapshot (every non-GGUF file in the repo, with progress aggregated across files
against the summed Hub-reported sizes).

Files stream directly via httpx rather than huggingface_hub's download helpers:
those manage their own internal tqdm bar with no progress-callback hook, so there's
no way to surface byte-level percent through them. Streaming ourselves against the
resolved HF URLs gives real progress at the cost of losing resume/retry handling --
an acceptable trade for a single-user tool where a failed download can just be
restarted.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
from huggingface_hub import hf_hub_url
from sqlmodel import Session

from app.config import get_settings
from app.db import DB_PATH, engine
from app.discovery.schemas import SnapshotFile
from app.models import DownloadedModelRecord, DownloadJob

MODELS_DIR = DB_PATH.parent / "models"


def run_download(job_id: int, repo_id: str, filename: str) -> None:
    """Runs synchronously -- called via FastAPI's BackgroundTasks, which executes sync
    callables in a thread pool so this doesn't block the event loop."""
    with Session(engine) as session:
        job = session.get(DownloadJob, job_id)
        if job is None:
            return

        job.status = "downloading"
        job.detail = "starting download"
        _save(session, job)

        dest_dir = MODELS_DIR / repo_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        last_reported_percent = -1

        def on_progress(downloaded_bytes: int, total_bytes: int) -> None:
            nonlocal last_reported_percent
            percent = int(downloaded_bytes / total_bytes * 100) if total_bytes else 0
            # Commit on whole-percent changes only -- a multi-GB file would otherwise
            # trigger thousands of SQLite writes for progress no poller can even see.
            if percent != last_reported_percent:
                job.percent = float(percent)
                job.detail = f"{downloaded_bytes // (1024 * 1024)} MB downloaded"
                _save(session, job)
                last_reported_percent = percent

        try:
            downloaded_bytes, total_bytes = _stream_to_file(
                dest_path, hf_hub_url(repo_id, filename), on_progress
            )
            if total_bytes and downloaded_bytes != total_bytes:
                raise OSError(
                    f"stream ended early: got {downloaded_bytes} of {total_bytes} bytes"
                )
        except (httpx.HTTPError, OSError) as e:
            dest_path.unlink(missing_ok=True)
            _fail_job(session, job, str(e))
            return

        _complete_job(
            session,
            job,
            repo_id=repo_id,
            backend="gguf",
            quant=filename,
            local_path=str(dest_path),
            size_bytes=dest_path.stat().st_size,
        )


def run_snapshot_download(job_id: int, repo_id: str, files: list[SnapshotFile]) -> None:
    """Downloads every file of a transformers snapshot into `models/<repo>/snapshot/`,
    preserving repo-relative subdirectories. The job row's `filename` tracks the file
    currently downloading; `percent` is aggregate bytes over the summed Hub sizes
    (files with unknown size contribute bytes but no total -- percent clamps at 99
    until the job completes, so it never reads 100% early)."""
    with Session(engine) as session:
        job = session.get(DownloadJob, job_id)
        if job is None:
            return

        if not files:
            job.status = "failed"
            job.error = f"No transformers snapshot files found for '{repo_id}'."
            job.detail = "download failed"
            _save(session, job)
            return

        job.status = "downloading"
        job.detail = "starting download"
        _save(session, job)

        dest_dir = MODELS_DIR / repo_id / "snapshot"
        dest_dir.mkdir(parents=True, exist_ok=True)
        total_bytes = sum(f.size_bytes or 0 for f in files)
        completed_bytes = 0
        last_reported_percent = -1

        try:
            for index, snapshot_file in enumerate(files, start=1):
                label = f"file {index}/{len(files)}: {snapshot_file.filename}"
                job.filename = snapshot_file.filename
                job.detail = label
                _save(session, job)

                base_bytes = completed_bytes

                def on_progress(
                    downloaded: int, _total: int, base: int = base_bytes, file_label: str = label
                ) -> None:
                    nonlocal last_reported_percent
                    overall = base + downloaded
                    percent = int(overall / total_bytes * 100) if total_bytes else 0
                    if percent != last_reported_percent:
                        job.percent = float(min(percent, 99))
                        job.detail = (
                            f"{file_label} "
                            f"({overall // (1024 * 1024)} MB "
                            f"of {total_bytes // (1024 * 1024)} MB)"
                        )
                        _save(session, job)
                        last_reported_percent = percent

                dest_path = dest_dir / snapshot_file.filename
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                written, declared = _stream_to_file(
                    dest_path, hf_hub_url(repo_id, snapshot_file.filename), on_progress
                )
                if declared and written != declared:
                    raise OSError(
                        f"stream ended early: got {written} of {declared} bytes "
                        f"for {snapshot_file.filename}"
                    )
                completed_bytes += written
        except (httpx.HTTPError, OSError) as e:
            # Remove only the snapshot dir -- a GGUF of the same repo downloaded
            # earlier lives alongside it and must survive.
            shutil.rmtree(dest_dir, ignore_errors=True)
            _fail_job(session, job, str(e))
            return

        _complete_job(
            session,
            job,
            repo_id=repo_id,
            backend="transformers",
            quant=None,
            local_path=str(dest_dir),
            size_bytes=completed_bytes,
        )


def _stream_to_file(
    dest_path: Path, url: str, on_progress: Callable[[int, int], None]
) -> tuple[int, int]:
    """Streams url to dest_path, calling on_progress(downloaded, total) after every
    chunk (both cumulative for this file). Returns (downloaded_bytes, total_bytes) so
    the caller can detect a stream that ended before the declared content-length -- a
    dropped connection mid-body raises no exception on its own, it just stops yielding
    chunks."""
    hf_api_key = get_settings().hf_api_key
    headers = {"Authorization": f"Bearer {hf_api_key}"} if hf_api_key else None
    with httpx.stream(
        "GET", url, headers=headers, follow_redirects=True, timeout=None
    ) as response:
        response.raise_for_status()
        total_bytes = int(response.headers.get("content-length", 0))
        downloaded_bytes = 0
        with dest_path.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded_bytes += len(chunk)
                on_progress(downloaded_bytes, total_bytes)
    return downloaded_bytes, total_bytes


def _save(session: Session, job: DownloadJob) -> None:
    job.updated_at = datetime.now(UTC)
    session.add(job)
    session.commit()


def _fail_job(session: Session, job: DownloadJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.detail = "download failed"
    _save(session, job)


def _complete_job(
    session: Session,
    job: DownloadJob,
    *,
    repo_id: str,
    backend: str,
    quant: str | None,
    local_path: str,
    size_bytes: int,
) -> None:
    record = DownloadedModelRecord(
        repo_id=repo_id,
        backend=backend,
        quant=quant,
        local_path=local_path,
        size_bytes=size_bytes,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    job.status = "completed"
    job.percent = 100.0
    job.detail = "download complete"
    job.downloaded_model_id = record.id
    _save(session, job)
