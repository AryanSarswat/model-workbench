"""POST /evals/run (SSE progress) + GET /evals/runs[/{id}/results] + GET
/evals/report + PATCH /evals/results/{id}.

The run streams progress for the lifetime of the request, persisting each case's
result as it goes so GET /evals/runs/{id}/results works from a second request.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.config import get_settings
from app.dataset.store import TestCase, load_cases
from app.db import get_session
from app.errors import WorkbenchError
from app.evals.report import build_eval_report
from app.evals.schemas import EvalReportRow, EvalRunRequest, ManualVerdictUpdate
from app.evals.service import run_one_case
from app.inference.base import InferenceBackend
from app.inference.registry import get_backend
from app.models import EvalResult, EvalRun

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/run")
def start_eval_run(request: EvalRunRequest, session: SessionDep) -> StreamingResponse:
    # Resolved pre-stream, like /chat/stream: a missing key, unknown backend, or
    # undownloaded model is a normal 4xx, not a broken stream with a stuck run.
    hf_api_key = get_settings().hf_api_key
    backend = get_backend(request.backend, request.model_id, hf_api_key)
    cases = load_cases(request.category)
    run = EvalRun(
        model_id=request.model_id,
        backend=request.backend,
        category=request.category,
        judge_model_id=request.judge_model_id,
        total_cases=len(cases),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return StreamingResponse(
        _run_events(session, run, cases, backend, hf_api_key), media_type="text/event-stream"
    )


def _event(run: EvalRun, current_case: str | None, done: bool, **extra: str) -> str:
    payload = {
        "completed": run.completed_cases,
        "total": run.total_cases,
        "current_case": current_case,
        "done": done,
        **extra,
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _run_events(
    session: Session,
    run: EvalRun,
    cases: list[TestCase],
    backend: InferenceBackend,
    hf_api_key: str | None,
) -> AsyncIterator[str]:
    # Per-case failures are recorded on the result by run_one_case; anything that
    # escapes here (or a client disconnect) ends the run as "failed", never "running".
    error: str | None = None
    try:
        for case in cases:
            yield _event(run, current_case=case.id, done=False)
            await run_one_case(session, run, case, backend, hf_api_key)
            run.completed_cases += 1
            session.add(run)
            session.commit()
        run.status = "completed"
    except Exception as exc:
        logger.exception("Eval run %s failed", run.id)
        error = str(exc)
    finally:
        await backend.aclose()
        if run.status != "completed":
            run.status = "failed"
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
    yield _event(run, current_case=None, done=True, **({"error": error} if error else {}))


@router.get("/runs")
def list_eval_runs(session: SessionDep) -> list[EvalRun]:
    return list(session.exec(select(EvalRun).order_by(EvalRun.created_at.desc())).all())


@router.get("/runs/{run_id}/results")
def get_eval_run_results(run_id: int, session: SessionDep) -> list[EvalResult]:
    run = session.get(EvalRun, run_id)
    if run is None:
        raise WorkbenchError(404, "eval_run_not_found", f"No eval run with id {run_id}.")
    return list(session.exec(select(EvalResult).where(EvalResult.run_id == run_id)).all())


@router.get("/report")
def get_eval_report(session: SessionDep) -> list[EvalReportRow]:
    return build_eval_report(session)


@router.patch("/results/{result_id}")
def update_eval_result(
    result_id: int, body: ManualVerdictUpdate, session: SessionDep
) -> EvalResult:
    result = session.get(EvalResult, result_id)
    if result is None:
        raise WorkbenchError(
            404, "eval_result_not_found", f"No eval result with id {result_id}."
        )
    result.manual_verdict = body.manual_verdict
    result.manual_notes = body.manual_notes
    session.add(result)
    session.commit()
    session.refresh(result)
    return result
