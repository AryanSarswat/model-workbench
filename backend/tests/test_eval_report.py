import json
from datetime import UTC, datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.evals.report import build_eval_report, result_passed
from app.models import EvalResult, EvalRun, ResponseMetricRecord


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _run(session: Session, **overrides) -> EvalRun:
    defaults = {"model_id": "some/model", "backend": "api", "total_cases": 1}
    defaults.update(overrides)
    run = EvalRun(**defaults)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _result(session: Session, run: EvalRun, **overrides) -> EvalResult:
    defaults = {
        "run_id": run.id,
        "case_id": "case-1",
        "category": "general",
        "response": "hi",
        "assertions_passed": 1,
        "assertions_total": 1,
        "assertions_detail": "[]",
    }
    defaults.update(overrides)
    result = EvalResult(**defaults)
    session.add(result)
    session.commit()
    session.refresh(result)
    return result


def test_build_eval_report_counts_only_latest_result_per_case():
    engine = _engine()
    with Session(engine) as session:
        run1 = _run(session)
        _result(
            session,
            run1,
            case_id="case-1",
            assertions_passed=1,
            assertions_total=1,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        # A later re-run of the same case that fails -- the stale passing result
        # from run1 must not be double-counted alongside it.
        run2 = _run(session)
        _result(
            session,
            run2,
            case_id="case-1",
            assertions_passed=0,
            assertions_total=1,
            created_at=datetime(2024, 1, 2, tzinfo=UTC),
        )

        rows = build_eval_report(session)

        assert len(rows) == 1
        row = rows[0]
        assert row.cases == 1
        assert row.passed == 0
        assert row.pass_rate == 0.0
        assert row.latest_run_id == run2.id


def test_result_passed_manual_verdict_overrides_automatic_outcome():
    failing_but_marked_pass = EvalResult(
        run_id=1,
        case_id="c",
        category="general",
        response="",
        assertions_passed=0,
        assertions_total=1,
        manual_verdict="pass",
    )
    passing_but_marked_fail = EvalResult(
        run_id=1,
        case_id="c",
        category="general",
        response="hi",
        assertions_passed=1,
        assertions_total=1,
        manual_verdict="fail",
    )

    assert result_passed(failing_but_marked_pass) is True
    assert result_passed(passing_but_marked_fail) is False


def test_result_passed_fails_on_error_or_low_judge_score():
    errored = EvalResult(
        run_id=1,
        case_id="c",
        category="general",
        response="",
        error="backend error",
        assertions_passed=1,
        assertions_total=1,
    )
    low_judge_score = EvalResult(
        run_id=1,
        case_id="c",
        category="general",
        response="hi",
        assertions_passed=1,
        assertions_total=1,
        judge_score=0.2,
    )
    passing_judge_score = EvalResult(
        run_id=1,
        case_id="c",
        category="general",
        response="hi",
        assertions_passed=1,
        assertions_total=1,
        judge_score=0.5,
    )

    assert result_passed(errored) is False
    assert result_passed(low_judge_score) is False
    assert result_passed(passing_judge_score) is True


def test_build_eval_report_reliability_none_vs_computed_and_avg_tokens_per_sec():
    engine = _engine()
    with Session(engine) as session:
        run = _run(session)

        metric_a = ResponseMetricRecord(
            model_id="some/model", backend="api", latency_ms=100.0, ram_used_gb=1.0,
            tokens_per_sec=10.0,
        )
        session.add(metric_a)
        session.commit()
        session.refresh(metric_a)
        metric_b = ResponseMetricRecord(
            model_id="some/model", backend="api", latency_ms=100.0, ram_used_gb=1.0,
            tokens_per_sec=20.0,
        )
        session.add(metric_b)
        session.commit()
        session.refresh(metric_b)

        # "plain" category never runs a schema_valid assertion -> reliability is
        # None (undefined), not zero.
        _result(
            session,
            run,
            case_id="case-1",
            category="plain",
            assertions_detail=json.dumps([{"type": "contains", "passed": True, "detail": ""}]),
            response_metric_id=metric_a.id,
        )
        # "structured" category runs schema_valid assertions -> reliability is
        # the share that passed.
        _result(
            session,
            run,
            case_id="case-2",
            category="structured",
            assertions_detail=json.dumps([{"type": "schema_valid", "passed": True, "detail": ""}]),
            response_metric_id=metric_b.id,
        )
        _result(
            session,
            run,
            case_id="case-3",
            category="structured",
            assertions_passed=0,
            assertions_total=1,
            assertions_detail=json.dumps(
                [{"type": "schema_valid", "passed": False, "detail": "x"}]
            ),
        )

        rows = {row.category: row for row in build_eval_report(session)}

        plain = rows["plain"]
        assert plain.structured_output_reliability is None
        assert plain.avg_tokens_per_sec == 10.0

        structured = rows["structured"]
        assert structured.structured_output_reliability == 0.5
        assert structured.avg_tokens_per_sec == 20.0  # only case-2 has a metric
