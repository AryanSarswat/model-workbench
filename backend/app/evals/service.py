"""Runs one test case through the same stream_chat() path used for regular chat.
The backend is resolved, and closed, once per run by evals/router.py.
"""

from __future__ import annotations

import json

from sqlmodel import Session

from app.dataset.store import TestCase
from app.errors import WorkbenchError
from app.evals.assertions import run_assertions
from app.evals.judge import score_with_judge
from app.inference.base import InferenceBackend
from app.inference.schemas import ChatMessage
from app.metrics import TurnRecorder
from app.models import EvalResult, EvalRun
from app.tools import resolve_tool_names


async def run_one_case(
    session: Session,
    run: EvalRun,
    case: TestCase,
    backend: InferenceBackend,
    hf_api_key: str | None,
) -> EvalResult:
    messages = list(case.messages)
    if case.system_prompt is not None:
        messages = [ChatMessage(role="system", content=case.system_prompt), *messages]
    tools = [tool.spec for tool in resolve_tool_names(case.expected_tools)] or None

    recorder = TurnRecorder()
    try:
        if case.output_schema is not None:
            backend.prevalidate_output_schema(case.output_schema)
        async for chunk in backend.stream_chat(
            run.model_id, messages, tools=tools, output_schema=case.output_schema
        ):
            recorder.observe(chunk)
    except WorkbenchError as exc:
        recorder.error = exc.message
    response_text = recorder.text

    metric = recorder.build_metric(run.model_id, run.backend)
    session.add(metric)
    session.commit()
    session.refresh(metric)

    capabilities = backend.capabilities()
    assertion_results = run_assertions(
        case, response_text, capabilities, recorder.tools_called, recorder.retries
    )

    judge_score = judge_rationale = None
    if case.judge is not None and run.judge_model_id is not None:
        judge_score, judge_rationale = await score_with_judge(
            run.backend, run.judge_model_id, hf_api_key, case, response_text
        )

    result = EvalResult(
        run_id=run.id,
        case_id=case.id,
        category=case.category,
        response=response_text,
        error=recorder.error,
        structured_output_mode=capabilities.structured_output_mode,
        native_tool_calling=capabilities.native_tool_calling,
        retries=recorder.retries,
        tools_called=",".join(recorder.tools_called),
        assertions_passed=sum(1 for a in assertion_results if a.passed),
        assertions_total=len(assertion_results),
        assertions_detail=json.dumps([a.model_dump() for a in assertion_results]),
        judge_score=judge_score,
        judge_rationale=judge_rationale,
        response_metric_id=metric.id,
    )
    session.add(result)
    session.commit()
    session.refresh(result)
    return result
