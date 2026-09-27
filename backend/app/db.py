"""SQLite persistence, per docs/architecture.md's data model.

Single-user, single-machine tool -- SQLite over Postgres because there's no server to run,
and over plain JSON files because this data needs real aggregation (unlike the test-case
dataset, which stays as hand-authored JSON on purpose).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import ACTIVE_DOWNLOAD_STATUSES, DownloadJob, EvalRun

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "workbench.db"
engine = create_engine(f"sqlite:///{DB_PATH}")


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def fail_interrupted_jobs(target: Engine = engine) -> None:
    """At startup nothing can still be running, so any download job or eval run left
    pending/downloading/running was cut off by a restart -- fail it rather than let the
    UI show it as live forever."""
    now = datetime.now(UTC)
    with Session(target) as session:
        interrupted_downloads = select(DownloadJob).where(
            DownloadJob.status.in_(ACTIVE_DOWNLOAD_STATUSES)
        )
        for job in session.exec(interrupted_downloads):
            job.status = "failed"
            job.error = "interrupted by a server restart"
            job.detail = "download failed"
            job.updated_at = now
            session.add(job)
        for run in session.exec(select(EvalRun).where(EvalRun.status == "running")):
            run.status = "failed"
            run.finished_at = now
            session.add(run)
        session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
