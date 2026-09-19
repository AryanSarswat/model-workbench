"""Downloaded-model management: list what's on disk, and remove it (DB record + files).

Actually downloading a model (POST /models/{id}/download) is a separate, follow-up piece --
this PR is just the persistence layer and the read/delete side of it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.errors import WorkbenchError
from app.models import DownloadedModelRecord

router = APIRouter(prefix="/models", tags=["downloads"])

SessionDep = Annotated[Session, Depends(get_session)]


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
