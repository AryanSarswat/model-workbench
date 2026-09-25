"""POST /evals/run (SSE progress) + GET /evals/runs[/{id}/results] + PATCH
/evals/results/{id} -- per docs/architecture.md's eval engine section.

Unlike downloads (BackgroundTasks + polling), evals are explicitly SSE in the
architecture doc: the run streams progress for the lifetime of the request,
the same shape as POST /chat/stream, persisting each case's result as it goes
so GET /evals/runs/{id}/results works even from a second request.
"""

from __future__ import annotations

import json
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
from app.evals.schemas import EvalRunRequest, ManualVerdictUpdate
from app.evals.service import run_one_case
from app.models import EvalResult, EvalRun

router = APIRouter(prefix="/evals", tags=["evals"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/run")
def start_eval_run(request: EvalRunRequest, session: SessionDep) -> StreamingResponse:
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
    hf_api_key = get_settings().hf_api_key
    return StreamingResponse(
        _run_events(session, run, cases, hf_api_key), media_type="text/event-stream"
    )


async def _run_events(
    session: Session, run: EvalRun, cases: list[TestCase], hf_api_key: str | None
) -> AsyncIterator[str]:
    for index, case in enumerate(cases):
        await run_one_case(session, run, case, hf_api_key)
        run.completed_cases += 1
        is_last = index == len(cases) - 1
        if is_last:
            run.status = "completed"
            run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        yield (
            "data: "
            + json.dumps(
                {
                    "completed": run.completed_cases,
                    "total": run.total_cases,
                    "current_case": None if is_last else case.id,
                    "done": is_last,
                }
            )
            + "\n\n"
        )


@router.get("/runs")
def list_eval_runs(session: SessionDep) -> list[EvalRun]:
    return list(session.exec(select(EvalRun).order_by(EvalRun.created_at.desc())).all())


@router.get("/runs/{run_id}/results")
def get_eval_run_results(run_id: int, session: SessionDep) -> list[EvalResult]:
    run = session.get(EvalRun, run_id)
    if run is None:
        raise WorkbenchError(404, "eval_run_not_found", f"No eval run with id {run_id}.")
    return list(session.exec(select(EvalResult).where(EvalResult.run_id == run_id)).all())


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
