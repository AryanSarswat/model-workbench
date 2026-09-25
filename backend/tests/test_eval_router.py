import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.dataset import store
from app.db import get_session
from app.evals import service
from app.inference.schemas import BackendCapabilities, ChatChunk
from app.main import app
from app.models import EvalResult, EvalRun

client = TestClient(app)

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _override_get_session():
    with Session(_test_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _reset_db_and_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "get_settings", lambda: Settings(_env_file=None, test_cases_dir=tmp_path)
    )
    SQLModel.metadata.create_all(_test_engine)
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override_get_session
    yield
    SQLModel.metadata.drop_all(_test_engine)
    if previous is not None:
        app.dependency_overrides[get_session] = previous
    else:
        app.dependency_overrides.pop(get_session, None)


class _FakeBackend:
    def capabilities(self):
        return BackendCapabilities(structured_output_mode="grammar", native_tool_calling=False)

    async def stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta="hi there")
        yield ChatChunk(done=True)

    async def aclose(self):
        pass


def _seed_case(category="general") -> dict:
    response = client.post(
        "/dataset/cases",
        json={
            "id": "case-1",
            "category": category,
            "messages": [{"role": "user", "content": "hi"}],
            "assertions": [{"type": "contains", "value": "hi"}],
        },
    )
    return response.json()


def test_start_eval_run_streams_progress_and_persists_results():
    _seed_case()

    with patch.object(service, "get_backend", return_value=_FakeBackend()):
        response = client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})

    assert response.status_code == 200
    events = [
        line[len("data: ") :] for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert len(events) == 1  # one case -> its progress event doubles as the final one
    assert json.loads(events[-1])["done"] is True

    with Session(_test_engine) as session:
        runs = list(session.exec(select(EvalRun)).all())
        results = list(session.exec(select(EvalResult)).all())
    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert runs[0].completed_cases == 1
    assert len(results) == 1
    assert results[0].response == "hi there"


def test_list_eval_runs_returns_newest_first():
    _seed_case()
    with patch.object(service, "get_backend", return_value=_FakeBackend()):
        client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})
        client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})

    response = client.get("/evals/runs")

    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == sorted(ids, reverse=True)


def test_get_eval_run_results_returns_404_for_missing_run():
    response = client.get("/evals/runs/9999/results")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "eval_run_not_found"


def test_get_eval_run_results_returns_its_results():
    _seed_case()
    with patch.object(service, "get_backend", return_value=_FakeBackend()):
        run_response = client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})
    assert run_response.status_code == 200
    with Session(_test_engine) as session:
        run_id = session.exec(select(EvalRun)).one().id

    response = client.get(f"/evals/runs/{run_id}/results")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_patch_eval_result_sets_manual_verdict():
    _seed_case()
    with patch.object(service, "get_backend", return_value=_FakeBackend()):
        client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})
    with Session(_test_engine) as session:
        result_id = session.exec(select(EvalResult)).one().id

    response = client.patch(
        f"/evals/results/{result_id}",
        json={"manual_verdict": "pass", "manual_notes": "looks right"},
    )

    assert response.status_code == 200
    assert response.json()["manual_verdict"] == "pass"
    assert response.json()["manual_notes"] == "looks right"


def test_patch_missing_eval_result_returns_404():
    response = client.patch(
        "/evals/results/9999", json={"manual_verdict": "pass", "manual_notes": None}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "eval_result_not_found"
