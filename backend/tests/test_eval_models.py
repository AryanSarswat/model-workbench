from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import EvalResult, EvalRun, ResponseMetricRecord


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_eval_run_and_result_round_trip_with_response_metric_link():
    engine = _engine()
    with Session(engine) as session:
        run = EvalRun(model_id="some/model", backend="api", total_cases=1)
        session.add(run)
        session.commit()
        session.refresh(run)

        metric = ResponseMetricRecord(
            model_id="some/model", backend="api", latency_ms=100.0, ram_used_gb=8.0
        )
        session.add(metric)
        session.commit()
        session.refresh(metric)

        result = EvalResult(
            run_id=run.id,
            case_id="case-1",
            category="general",
            response="hi",
            response_metric_id=metric.id,
        )
        session.add(result)
        session.commit()

        stored = session.exec(select(EvalResult).where(EvalResult.run_id == run.id)).one()
        assert stored.case_id == "case-1"
        assert stored.response_metric_id == metric.id
        assert stored.manual_verdict is None
