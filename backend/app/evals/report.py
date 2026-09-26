"""Aggregates eval_results into the model-comparison report the frontend's Evals
screen renders: rows = (model_id, backend), columns = category.
"""

from __future__ import annotations

import json
from collections import defaultdict

from sqlmodel import Session, select

from app.evals.schemas import EvalReportRow
from app.models import EvalResult, EvalRun, ResponseMetricRecord


def result_passed(result: EvalResult) -> bool:
    """Whether a single eval result counts as a pass for reporting purposes.

    `manual_verdict` always wins when set ("pass" or "fail"). Otherwise a result
    passes iff it did not error, all of its assertions passed, and (when a judge
    scored it) the judge score is at least 0.5. The frontend mirrors this rule.
    """
    if result.manual_verdict == "pass":
        return True
    if result.manual_verdict == "fail":
        return False
    return (
        result.error is None
        and result.assertions_passed == result.assertions_total
        and (result.judge_score is None or result.judge_score >= 0.5)
    )


def build_eval_report(session: Session) -> list[EvalReportRow]:
    """Builds the report, sorted by model_id, backend, category.

    Only the latest result per (model_id, backend, case_id) counts -- latest by
    EvalResult.created_at, then id -- so re-running a model doesn't double-count
    cases. Results from runs of any status count.
    """
    rows = session.exec(
        select(EvalResult, EvalRun.model_id, EvalRun.backend).join(
            EvalRun, EvalResult.run_id == EvalRun.id
        )
    ).all()

    latest_by_case: dict[tuple[str, str, str], EvalResult] = {}
    for result, model_id, backend in rows:
        key = (model_id, backend, result.case_id)
        current = latest_by_case.get(key)
        if current is None or (result.created_at, result.id) > (current.created_at, current.id):
            latest_by_case[key] = result

    groups: dict[tuple[str, str, str], list[EvalResult]] = defaultdict(list)
    for (model_id, backend, _case_id), result in latest_by_case.items():
        groups[(model_id, backend, result.category)].append(result)

    metric_ids = {
        r.response_metric_id for r in latest_by_case.values() if r.response_metric_id is not None
    }
    metrics = {
        metric.id: metric
        for metric in session.exec(
            select(ResponseMetricRecord).where(ResponseMetricRecord.id.in_(metric_ids))
        ).all()
    }

    report_rows = []
    for (model_id, backend, category), results in groups.items():
        cases = len(results)
        passed = sum(1 for result in results if result_passed(result))
        linked = [metrics[r.response_metric_id] for r in results if r.response_metric_id in metrics]
        tokens_per_sec = [m.tokens_per_sec for m in linked if m.tokens_per_sec is not None]
        ttft_ms = [m.ttft_ms for m in linked if m.ttft_ms is not None]

        schema_assertions: list[bool] = []
        tool_assertions: list[bool] = []
        for result in results:
            for assertion in json.loads(result.assertions_detail):
                if assertion["type"] == "schema_valid":
                    schema_assertions.append(assertion["passed"])
                elif assertion["type"] == "tool_called":
                    tool_assertions.append(assertion["passed"])

        latest_result = max(results, key=lambda result: (result.created_at, result.id))

        report_rows.append(
            EvalReportRow(
                model_id=model_id,
                backend=backend,
                category=category,
                cases=cases,
                passed=passed,
                pass_rate=passed / cases,
                avg_tokens_per_sec=(
                    sum(tokens_per_sec) / len(tokens_per_sec) if tokens_per_sec else None
                ),
                avg_ttft_ms=sum(ttft_ms) / len(ttft_ms) if ttft_ms else None,
                structured_output_reliability=(
                    sum(schema_assertions) / len(schema_assertions)
                    if schema_assertions
                    else None
                ),
                tool_calling_reliability=(
                    sum(tool_assertions) / len(tool_assertions) if tool_assertions else None
                ),
                latest_run_id=latest_result.run_id,
            )
        )

    report_rows.sort(key=lambda row: (row.model_id, row.backend, row.category))
    return report_rows
