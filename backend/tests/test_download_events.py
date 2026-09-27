"""GET /models/downloads/events: download progress pushed over SSE instead of polled."""

import asyncio
import json
from unittest.mock import patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.downloads import events
from app.models import DownloadJob
from tests.test_downloads import client

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _session() -> Session:
    return Session(_engine)


def _add(**fields) -> int:
    with _session() as session:
        job = DownloadJob(repo_id="org/model", **fields)
        session.add(job)
        session.commit()
        return job.id


def _update(job_id: int, **fields) -> None:
    with _session() as session:
        job = session.get(DownloadJob, job_id)
        for key, value in fields.items():
            setattr(job, key, value)
        session.add(job)
        session.commit()


def _job(event: str) -> dict:
    assert event.startswith("data: ") and event.endswith("\n\n"), event
    return json.loads(event.removeprefix("data: "))


def test_streams_active_jobs_then_each_change_through_to_the_final_state():
    SQLModel.metadata.create_all(_engine)
    _add(status="completed")  # finished before connecting: never sent
    running = _add(status="downloading", percent=10)

    async def scenario() -> list[dict]:
        stream = events.job_events(_session, poll_seconds=0.01)
        seen = [_job(await anext(stream))]
        _update(running, percent=55)
        seen.append(_job(await anext(stream)))
        # Started and finished between two polls: the client still hears how it ended.
        _add(status="failed", error="disk full")
        _update(running, status="completed", percent=100)
        seen += [_job(await anext(stream)), _job(await anext(stream))]
        await stream.aclose()
        return seen

    seen = asyncio.run(scenario())
    SQLModel.metadata.drop_all(_engine)

    assert [(j["id"], j["status"], j["percent"]) for j in seen] == [
        (running, "downloading", 10),
        (running, "downloading", 55),
        (running, "completed", 100),
        (running + 1, "failed", 0.0),
    ]


def test_sends_a_heartbeat_comment_while_nothing_changes():
    SQLModel.metadata.create_all(_engine)

    async def first_event() -> str:
        stream = events.job_events(_session, poll_seconds=0.01, heartbeat_seconds=0.02)
        event = await anext(stream)
        await stream.aclose()
        return event

    assert asyncio.run(first_event()) == ": ping\n\n"
    SQLModel.metadata.drop_all(_engine)


def test_events_route_is_not_parsed_as_a_job_id():
    async def one_event(*_args, **_kwargs):
        yield ": ping\n\n"

    with patch("app.downloads.router.job_events", one_event):
        response = client.get("/models/downloads/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == ": ping\n\n"
