"""Executes a GGUF file download in the background, tracking progress on a DownloadJob row.

Streams the file directly via httpx rather than huggingface_hub's hf_hub_download: hf_hub_download
manages its own internal tqdm bar with no progress-callback hook, so there's no way to surface
byte-level percent through it. Streaming ourselves against the resolved HF URL gives real progress
at the cost of losing hf_hub_download's resume/retry handling -- an acceptable trade for a single-
user tool where a failed download can just be restarted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
from huggingface_hub import hf_hub_url
from sqlmodel import Session

from app.config import get_settings
from app.db import DB_PATH, engine
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

        try:
            downloaded_bytes, total_bytes = _stream_to_file(
                dest_path, hf_hub_url(repo_id, filename), session, job
            )
            if total_bytes and downloaded_bytes != total_bytes:
                raise OSError(
                    f"stream ended early: got {downloaded_bytes} of {total_bytes} bytes"
                )
        except (httpx.HTTPError, OSError) as e:
            dest_path.unlink(missing_ok=True)
            job.status = "failed"
            job.error = str(e)
            job.detail = "download failed"
            _save(session, job)
            return

        record = DownloadedModelRecord(
            repo_id=repo_id,
            backend="gguf",
            quant=filename,
            local_path=str(dest_path),
            size_bytes=dest_path.stat().st_size,
        )
        session.add(record)
        session.commit()
        session.refresh(record)

        job.status = "completed"
        job.percent = 100.0
        job.detail = "download complete"
        job.downloaded_model_id = record.id
        _save(session, job)


def _stream_to_file(
    dest_path: Path, url: str, session: Session, job: DownloadJob
) -> tuple[int, int]:
    """Returns (downloaded_bytes, total_bytes) so the caller can detect a stream that
    ended before the declared content-length -- a dropped connection mid-body raises no
    exception on its own, it just stops yielding chunks."""
    last_reported_percent = -1
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
                percent = int(downloaded_bytes / total_bytes * 100) if total_bytes else 0
                # Commit on whole-percent changes only -- a multi-GB file would otherwise
                # trigger thousands of SQLite writes for progress no poller can even see.
                if percent != last_reported_percent:
                    job.percent = float(percent)
                    job.detail = f"{downloaded_bytes // (1024 * 1024)} MB downloaded"
                    _save(session, job)
                    last_reported_percent = percent
    return downloaded_bytes, total_bytes


def _save(session: Session, job: DownloadJob) -> None:
    job.updated_at = datetime.now(UTC)
    session.add(job)
    session.commit()
