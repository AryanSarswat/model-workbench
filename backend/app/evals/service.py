"""Runs one test case through the same chat path used for regular chat --
get_backend() + stream_chat() -- per docs/architecture.md's eval engine design.
No eval-specific inference logic: assertions, judge scoring, and
response_metrics all run on top of the same InferenceBackend Protocol every
other caller uses. The per-run orchestration loop (iterating every matching
case, SSE progress) lives in evals/router.py, since it's inherently tied to
the StreamingResponse the endpoint returns.
"""

from __future__ import annotations

import json
import time

from sqlmodel import Session

from app.dataset.store import TestCase
from app.evals.assertions import run_assertions
from app.evals.judge import score_with_judge
from app.inference.registry import get_backend
from app.inference.schemas import ChatMessage, TokenUsage
from app.metrics import build_response_metric
from app.models import EvalResult, EvalRun
from app.tools import resolve_tool_names


async def run_one_case(
    session: Session, run: EvalRun, case: TestCase, hf_api_key: str | None
) -> EvalResult:
    backend = get_backend(run.backend, run.model_id, hf_api_key)
    messages = list(case.messages)
    if case.system_prompt is not None:
        messages = [ChatMessage(role="system", content=case.system_prompt), *messages]
    tools = [tool.spec for tool in resolve_tool_names(case.expected_tools)] or None

    started_at = time.monotonic()
    first_chunk_at: float | None = None
    parts: list[str] = []
    usage: TokenUsage | None = None
    tools_called: list[str] = []
    retries = 0
    try:
        async for chunk in backend.stream_chat(
            run.model_id, messages, tools=tools, output_schema=case.output_schema
        ):
            if chunk.error is None and chunk.delta:
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic()
                parts.append(chunk.delta)
            if chunk.done:
                usage = chunk.usage
                tools_called = chunk.tools_called
                retries = chunk.retries
    finally:
        await backend.aclose()
    finished_at = time.monotonic()
    response_text = "".join(parts)

    metric = build_response_metric(
        model_id=run.model_id,
        backend_name=run.backend,
        usage=usage,
        started_at=started_at,
        first_chunk_at=first_chunk_at,
        finished_at=finished_at,
    )
    session.add(metric)
    session.commit()
    session.refresh(metric)

    capabilities = backend.capabilities()
    assertion_results = run_assertions(case, response_text, capabilities, tools_called, retries)

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
        structured_output_mode=capabilities.structured_output_mode,
        native_tool_calling=capabilities.native_tool_calling,
        retries=retries,
        tools_called=",".join(tools_called),
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
