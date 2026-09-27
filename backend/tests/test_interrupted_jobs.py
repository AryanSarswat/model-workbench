"""Jobs left mid-flight by a restart are failed on startup, not shown as running forever."""

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db import fail_interrupted_jobs
from app.models import DownloadJob, EvalRun


def test_startup_fails_jobs_a_restart_interrupted_and_leaves_finished_ones_alone():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                DownloadJob(repo_id="a/pending", status="pending"),
                DownloadJob(repo_id="a/downloading", status="downloading", percent=40),
                DownloadJob(repo_id="a/done", status="completed", percent=100),
                EvalRun(model_id="m", backend="gguf", status="running"),
                EvalRun(model_id="m", backend="gguf", status="completed"),
            ]
        )
        session.commit()

    fail_interrupted_jobs(engine)

    with Session(engine) as session:
        jobs = {j.repo_id: j for j in session.exec(select(DownloadJob)).all()}
        runs = session.exec(select(EvalRun).order_by(EvalRun.id)).all()
    assert [jobs[r].status for r in ("a/pending", "a/downloading", "a/done")] == [
        "failed",
        "failed",
        "completed",
    ]
    assert "restart" in jobs["a/downloading"].error
    assert jobs["a/done"].error is None
    assert [r.status for r in runs] == ["failed", "completed"]
    assert runs[0].finished_at is not None
