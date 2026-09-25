import asyncio

import pytest

from app.dataset.store import TestCase, TestCaseJudge
from app.errors import WorkbenchError
from app.evals import judge
from app.inference.schemas import ChatChunk, ChatMessage


class _FakeBackend:
    def __init__(self, reply: str | None = None, error: str | None = None):
        self._reply = reply
        self._error = error
        self.closed = False

    async def stream_chat(self, model_id, messages, tools=None, output_schema=None):
        if self._error is not None:
            yield ChatChunk(done=True, error=self._error)
            return
        yield ChatChunk(delta=self._reply)
        yield ChatChunk(done=True)

    async def aclose(self):
        self.closed = True


def _case() -> TestCase:
    return TestCase(
        id="case-1",
        category="general",
        messages=[ChatMessage(role="user", content="hi")],
        judge=TestCaseJudge(criteria="Must be polite."),
    )


def test_score_with_judge_parses_score_and_rationale(monkeypatch):
    fake = _FakeBackend(reply='{"score": 0.8, "rationale": "Polite and on-topic."}')
    monkeypatch.setattr(judge, "get_backend", lambda *a, **k: fake)

    score, rationale = asyncio.run(
        judge.score_with_judge("api", "judge/model", "fake-key", _case(), "hi there")
    )

    assert score == 0.8
    assert rationale == "Polite and on-topic."
    assert fake.closed is True


def test_score_with_judge_clamps_out_of_range_scores(monkeypatch):
    fake = _FakeBackend(reply='{"score": 1.5, "rationale": "great"}')
    monkeypatch.setattr(judge, "get_backend", lambda *a, **k: fake)

    score, _ = asyncio.run(
        judge.score_with_judge("api", "judge/model", "fake-key", _case(), "hi")
    )

    assert score == 1.0


def test_score_with_judge_returns_zero_on_unparseable_reply(monkeypatch):
    fake = _FakeBackend(reply="not json at all")
    monkeypatch.setattr(judge, "get_backend", lambda *a, **k: fake)

    score, rationale = asyncio.run(
        judge.score_with_judge("api", "judge/model", "fake-key", _case(), "hi")
    )

    assert score == 0.0
    assert "not valid JSON" in rationale


def test_score_with_judge_rejects_a_boolean_score(monkeypatch):
    fake = _FakeBackend(reply='{"score": true, "rationale": "great"}')
    monkeypatch.setattr(judge, "get_backend", lambda *a, **k: fake)

    score, rationale = asyncio.run(
        judge.score_with_judge("api", "judge/model", "fake-key", _case(), "hi")
    )

    assert score == 0.0
    assert "not valid JSON" in rationale


def test_score_with_judge_returns_zero_on_backend_error(monkeypatch):
    fake = _FakeBackend(error="model unavailable")
    monkeypatch.setattr(judge, "get_backend", lambda *a, **k: fake)

    score, rationale = asyncio.run(
        judge.score_with_judge("api", "judge/model", "fake-key", _case(), "hi")
    )

    assert score == 0.0
    assert "model unavailable" in rationale


def test_score_with_judge_raises_when_case_has_no_judge_criteria():
    case = TestCase(
        id="case-1", category="general", messages=[ChatMessage(role="user", content="hi")]
    )

    async def _call():
        return await judge.score_with_judge("api", "judge/model", "fake-key", case, "hi")

    with pytest.raises(WorkbenchError) as exc_info:
        asyncio.run(_call())

    assert exc_info.value.code == "no_judge_criteria"
