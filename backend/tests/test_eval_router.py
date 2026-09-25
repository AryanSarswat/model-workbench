import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.dataset import store
from app.db import get_session
from app.errors import WorkbenchError
from app.evals import router as eval_router
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
    closed = False

    def capabilities(self):
        return BackendCapabilities(structured_output_mode="grammar", native_tool_calling=False)

    async def stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta="hi there")
        yield ChatChunk(done=True)

    def prevalidate_output_schema(self, schema):
        pass

    async def aclose(self):
        self.closed = True


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


def _events(response) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_start_eval_run_streams_progress_and_persists_results():
    case = _seed_case()
    backend = _FakeBackend()

    with patch.object(eval_router, "get_backend", return_value=backend):
        response = client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})

    assert response.status_code == 200
    events = _events(response)
    # One "now running X" event per case, then a final done event.
    assert events[0] == {"completed": 0, "total": 1, "current_case": case["id"], "done": False}
    assert events[-1]["done"] is True
    assert events[-1]["completed"] == 1
    assert backend.closed is True

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
    with patch.object(eval_router, "get_backend", return_value=_FakeBackend()):
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
    with patch.object(eval_router, "get_backend", return_value=_FakeBackend()):
        run_response = client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})
    assert run_response.status_code == 200
    with Session(_test_engine) as session:
        run_id = session.exec(select(EvalRun)).one().id

    response = client.get(f"/evals/runs/{run_id}/results")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_patch_eval_result_sets_manual_verdict():
    _seed_case()
    with patch.object(eval_router, "get_backend", return_value=_FakeBackend()):
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


def test_misconfigured_backend_is_a_400_before_any_run_is_created():
    _seed_case()
    missing_key = WorkbenchError(400, "missing_hf_api_key", "HF_API_KEY is not configured")

    with patch.object(eval_router, "get_backend", side_effect=missing_key):
        response = client.post("/evals/run", json={"model_id": "some/model", "backend": "api"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_hf_api_key"
    with Session(_test_engine) as session:
        assert session.exec(select(EvalRun)).all() == []


def test_run_with_no_matching_cases_completes_instead_of_hanging_as_running():
    with patch.object(eval_router, "get_backend", return_value=_FakeBackend()):
        response = client.post(
            "/evals/run", json={"model_id": "some/model", "backend": "api", "category": "none"}
        )

    assert _events(response) == [{"completed": 0, "total": 0, "current_case": None, "done": True}]
    with Session(_test_engine) as session:
        assert session.exec(select(EvalRun)).one().status == "completed"
