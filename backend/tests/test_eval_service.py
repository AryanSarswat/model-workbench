import asyncio

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.dataset.store import Assertion, TestCase, TestCaseJudge
from app.evals import service
from app.inference.schemas import BackendCapabilities, ChatChunk, ChatMessage, TokenUsage
from app.models import EvalRun


class _FakeBackend:
    def __init__(
        self, reply="hi", tools_called=None, retries=0, usage=None, capabilities=None
    ):
        self._reply = reply
        self._tools_called = tools_called or []
        self._retries = retries
        self._usage = usage
        self._capabilities = capabilities or BackendCapabilities(
            structured_output_mode="grammar", native_tool_calling=False
        )
        self.closed = False

    def capabilities(self):
        return self._capabilities

    async def stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta=self._reply)
        yield ChatChunk(
            done=True, usage=self._usage, tools_called=self._tools_called, retries=self._retries
        )

    async def aclose(self):
        self.closed = True


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _run(session, **overrides) -> EvalRun:
    defaults = {"model_id": "some/model", "backend": "api", "total_cases": 1}
    defaults.update(overrides)
    run = EvalRun(**defaults)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _case(**overrides) -> TestCase:
    defaults = {
        "id": "case-1",
        "category": "general",
        "messages": [ChatMessage(role="user", content="hi")],
        "assertions": [Assertion(type="contains", value="hi")],
    }
    defaults.update(overrides)
    return TestCase(**defaults)


def test_run_one_case_persists_response_metric_and_result(monkeypatch):
    fake = _FakeBackend(reply="hi there", usage=TokenUsage(prompt_tokens=5, completion_tokens=2))
    monkeypatch.setattr(service, "get_backend", lambda *a, **k: fake)
    engine = _engine()
    with Session(engine) as session:
        run = _run(session)

        result = asyncio.run(service.run_one_case(session, run, _case(), "fake-key"))

        assert result.response == "hi there"
        assert result.assertions_passed == 1
        assert result.assertions_total == 1
        assert result.response_metric_id is not None
        assert fake.closed is True


def test_run_one_case_records_tools_called_and_retries(monkeypatch):
    fake = _FakeBackend(reply="5", tools_called=["calculator"], retries=1)
    monkeypatch.setattr(service, "get_backend", lambda *a, **k: fake)
    engine = _engine()
    with Session(engine) as session:
        run = _run(session)
        case = _case(assertions=[Assertion(type="tool_called", name="calculator")])

        result = asyncio.run(service.run_one_case(session, run, case, "fake-key"))

        assert result.tools_called == "calculator"
        assert result.retries == 1
        assert result.assertions_passed == 1


def test_run_one_case_runs_judge_when_case_has_criteria_and_run_has_judge_model(monkeypatch):
    fake = _FakeBackend(reply="hi there")
    monkeypatch.setattr(service, "get_backend", lambda *a, **k: fake)

    async def fake_score(backend_name, judge_model_id, hf_api_key, case, response):
        return 0.9, "Very polite."

    monkeypatch.setattr(service, "score_with_judge", fake_score)
    engine = _engine()
    with Session(engine) as session:
        run = _run(session, judge_model_id="judge/model")
        case = _case(judge=TestCaseJudge(criteria="Must be polite."), assertions=[])

        result = asyncio.run(service.run_one_case(session, run, case, "fake-key"))

        assert result.judge_score == 0.9
        assert result.judge_rationale == "Very polite."


def test_run_one_case_skips_judge_when_run_has_no_judge_model_id(monkeypatch):
    fake = _FakeBackend(reply="hi there")
    monkeypatch.setattr(service, "get_backend", lambda *a, **k: fake)
    engine = _engine()
    with Session(engine) as session:
        run = _run(session)  # no judge_model_id
        case = _case(judge=TestCaseJudge(criteria="Must be polite."), assertions=[])

        result = asyncio.run(service.run_one_case(session, run, case, "fake-key"))

        assert result.judge_score is None
        assert result.judge_rationale is None
