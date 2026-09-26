"""Downloaded-model management: list/remove what's on disk, and kick off new downloads.

Two download kinds: a single GGUF file (`filename` from `GET /models/{id}`'s
gguf_files), or a full transformers snapshot (`snapshot: true` -- every non-GGUF file
in the repo, for the transformers backend). Progress for both is polled via
`GET /models/downloads/{job_id}`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.discovery.hf_client import get_model_detail, get_snapshot_files
from app.downloads.service import run_download, run_snapshot_download
from app.errors import WorkbenchError
from app.models import DownloadedModelRecord, DownloadJob

router = APIRouter(prefix="/models", tags=["downloads"])

SessionDep = Annotated[Session, Depends(get_session)]


class DownloadRequest(BaseModel):
    filename: str | None = None  # one of the GGUF filenames from GET /models/{id}
    snapshot: bool = False  # whole transformers snapshot instead of one GGUF file


@router.get("/downloaded")
def list_downloaded(session: SessionDep) -> list[DownloadedModelRecord]:
    return list(session.exec(select(DownloadedModelRecord)).all())


@router.delete("/downloaded/{record_id}", status_code=204)
def delete_downloaded(record_id: int, session: SessionDep) -> None:
    record = session.get(DownloadedModelRecord, record_id)
    if record is None:
        raise WorkbenchError(
            status_code=404,
            code="download_not_found",
            message=f"No downloaded model record with id {record_id}.",
        )

    path = Path(record.local_path)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()

    session.delete(record)
    session.commit()


@router.get("/downloads")
def list_download_jobs(session: SessionDep, active: bool = False) -> list[DownloadJob]:
    """Every download job, newest first; `active=true` keeps only pending/downloading."""
    query = select(DownloadJob)
    if active:
        query = query.where(DownloadJob.status.in_(["pending", "downloading"]))
    query = query.order_by(DownloadJob.created_at.desc(), DownloadJob.id.desc())
    return list(session.exec(query).all())


@router.get("/downloads/{job_id}")
def get_download_job(job_id: int, session: SessionDep) -> DownloadJob:
    job = session.get(DownloadJob, job_id)
    if job is None:
        raise WorkbenchError(
            status_code=404,
            code="download_job_not_found",
            message=f"No download job with id {job_id}.",
        )
    return job


# NOTE: the trailing "/download" literal keeps this from colliding with the two static
# routes above (or discovery_router's /{model_id:path} catch-all) regardless of order --
# {model_id:path} is greedy but nothing else in this file or discovery_router ends in a
# literal "/download" segment.
@router.post("/{model_id:path}/download", status_code=202)
def start_download(
    model_id: str,
    body: DownloadRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> DownloadJob:
    if bool(body.filename) == body.snapshot:
        raise WorkbenchError(
            status_code=400,
            code="invalid_download_request",
            message="Provide either 'filename' (one GGUF file) or 'snapshot: true'.",
        )

    if body.snapshot:
        files = get_snapshot_files(model_id)
        if not files:
            raise WorkbenchError(
                status_code=400,
                code="no_transformers_snapshot",
                message=f"'{model_id}' has no non-GGUF files to snapshot.",
            )
        job = _create_job(session, model_id, kind="snapshot")
        background_tasks.add_task(run_snapshot_download, job.id, model_id, files)
        return job

    detail = get_model_detail(model_id)
    available = {f.filename for f in detail.gguf_files}
    if body.filename not in available:
        raise WorkbenchError(
            status_code=400,
            code="invalid_gguf_filename",
            message=f"'{body.filename}' is not a GGUF file in {model_id}.",
            details={"available": sorted(available)},
        )

    job = _create_job(session, model_id, kind="gguf", filename=body.filename)
    background_tasks.add_task(run_download, job.id, model_id, body.filename)
    return job


def _create_job(
    session: Session, repo_id: str, kind: str, filename: str | None = None
) -> DownloadJob:
    job = DownloadJob(repo_id=repo_id, kind=kind, filename=filename)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
