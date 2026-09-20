import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.db import get_session
from app.errors import WorkbenchError
from app.inference import registry
from app.inference.schemas import ChatChunk, TokenUsage
from app.main import app
from app.models import ResponseMetricRecord

client = TestClient(app)

_REQUEST = {"model_id": "some/model", "messages": [{"role": "user", "content": "hi"}]}

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _override_get_session():
    with Session(_test_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _reset_db():
    # Every chat turn now writes a response_metrics row unconditionally (Task 8) --
    # without this override these tests would hit the real data/workbench.db.
    SQLModel.metadata.create_all(_test_engine)
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override_get_session
    yield
    SQLModel.metadata.drop_all(_test_engine)
    if previous is not None:
        app.dependency_overrides[get_session] = previous
    else:
        app.dependency_overrides.pop(get_session, None)


def test_stream_chat_returns_400_when_api_key_missing():
    with patch("app.chat.router.get_settings", return_value=Settings(hf_api_key=None)):
        response = client.post("/chat/stream", json=_REQUEST)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_hf_api_key"


def test_stream_chat_rejects_unsupported_backend():
    response = client.post("/chat/stream", json={**_REQUEST, "backend": "nope"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "backend_not_supported"


def test_stream_chat_gguf_without_download_returns_404(monkeypatch):
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(registry, "engine", test_engine)

    response = client.post("/chat/stream", json={**_REQUEST, "backend": "gguf"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "local_model_not_found"


def test_stream_chat_streams_sse_events_from_the_backend():
    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta="Hel")
        yield ChatChunk(delta="lo")
        yield ChatChunk(done=True)

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        response = client.post("/chat/stream", json=_REQUEST)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [(e["delta"], e["done"], e["error"]) for e in events] == [
        ("Hel", False, None),
        ("lo", False, None),
        ("", True, None),
    ]
    for event in events:
        assert event["usage"] is None
        assert event["tools_called"] == []
        assert event["retries"] == 0


def test_stream_chat_closes_the_backend_after_streaming():
    """A fresh HFInferenceAPIBackend (and its httpx connection pool) is created per
    request -- leaving it open would leak a connection on every chat request."""
    closed = []

    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(done=True)

    async def fake_aclose(self):
        closed.append(True)

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.aclose", fake_aclose),
    ):
        client.post("/chat/stream", json=_REQUEST)

    assert closed == [True]


def test_stream_chat_passes_resolved_tool_specs_to_the_backend():
    seen = {}

    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        seen["tools"] = tools
        yield ChatChunk(done=True)

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        response = client.post("/chat/stream", json={**_REQUEST, "tools": ["calculator"]})

    assert response.status_code == 200
    assert [spec.name for spec in seen["tools"]] == ["calculator"]


def test_stream_chat_rejects_unknown_tool_name():
    with patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")):
        response = client.post("/chat/stream", json={**_REQUEST, "tools": ["nope"]})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_tool"


def test_stream_chat_passes_output_schema_to_the_backend():
    seen = {}

    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        seen["output_schema"] = output_schema
        yield ChatChunk(done=True)

    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        response = client.post("/chat/stream", json={**_REQUEST, "output_schema": schema})

    assert response.status_code == 200
    assert seen["output_schema"] == schema


def test_stream_chat_rejects_invalid_output_schema_before_streaming():
    def _reject(self, schema):
        raise WorkbenchError(400, "invalid_output_schema", "bad schema")

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch(
            "app.inference.hf_api_backend.HFInferenceAPIBackend.prevalidate_output_schema",
            _reject,
        ),
    ):
        response = client.post(
            "/chat/stream", json={**_REQUEST, "output_schema": {"type": "object"}}
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_output_schema"


def _metrics_in_db() -> list[ResponseMetricRecord]:
    with Session(_test_engine) as session:
        return list(session.exec(select(ResponseMetricRecord)).all())


def test_stream_chat_persists_a_response_metric_for_every_turn():
    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta="Hel")
        yield ChatChunk(delta="lo")
        yield ChatChunk(done=True, usage=TokenUsage(prompt_tokens=5, completion_tokens=3))

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        response = client.post("/chat/stream", json=_REQUEST)

    assert response.status_code == 200
    metrics = _metrics_in_db()
    assert len(metrics) == 1
    assert metrics[0].model_id == "some/model"
    assert metrics[0].backend == "api"
    assert metrics[0].prompt_tokens == 5
    assert metrics[0].completion_tokens == 3
    assert metrics[0].latency_ms > 0


def test_stream_chat_persists_a_response_metric_even_when_the_backend_errors():
    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta="partial")
        yield ChatChunk(done=True, error="boom")

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        response = client.post("/chat/stream", json=_REQUEST)

    assert response.status_code == 200
    metrics = _metrics_in_db()
    assert len(metrics) == 1
    assert metrics[0].completion_tokens is None  # no usage on an error chunk
