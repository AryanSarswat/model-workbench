"""Download progress as a server-sent event stream (GET /models/downloads/events).

Download threads write progress to the download_jobs table (service.py), so the
stream reads that table on a short server-side interval and sends a job whenever
its row changed. Clients get every active job on connect, then each change through
to the job's final completed/failed state -- no re-fetch to learn how it ended.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

from sqlalchemy import or_
from sqlmodel import Session, select

from app import db
from app.models import DownloadJob

POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15.0
_ACTIVE = ("pending", "downloading")


def _default_session() -> Session:
    return Session(db.engine)


async def job_events(
    session_factory: Callable[[], Session] = _default_session,
    poll_seconds: float = POLL_SECONDS,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
) -> AsyncIterator[str]:
    """Yield `data: <DownloadJob JSON>` per changed job, and a `: ping` comment after
    heartbeat_seconds without one. Runs until the client disconnects."""
    sent: dict[int, str] = {}  # job id -> last JSON sent
    with session_factory() as session:
        # Jobs created after connecting are followed even if they finish between polls.
        newest_at_connect = max(session.exec(select(DownloadJob.id)).all(), default=0)
    idle = 0.0
    while True:
        with session_factory() as session:
            query = select(DownloadJob).where(
                or_(
                    DownloadJob.status.in_(_ACTIVE),
                    DownloadJob.id > newest_at_connect,
                    DownloadJob.id.in_(list(sent)),
                )
            )
            jobs = session.exec(query.order_by(DownloadJob.id)).all()
        changed = [job for job in jobs if sent.get(job.id) != job.model_dump_json()]
        for job in changed:
            sent[job.id] = job.model_dump_json()
            yield f"data: {sent[job.id]}\n\n"
        idle = 0.0 if changed else idle + poll_seconds
        if idle >= heartbeat_seconds:
            idle = 0.0
            yield ": ping\n\n"
        await asyncio.sleep(poll_seconds)
