from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from app.config import Settings
from app.errors import WorkbenchError
from app.inference import registry
from app.inference.schemas import ChatChunk
from app.main import app

client = TestClient(app)

_REQUEST = {"model_id": "some/model", "messages": [{"role": "user", "content": "hi"}]}


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
    events = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert events == [
        'data: {"delta":"Hel","done":false,"error":null}',
        'data: {"delta":"lo","done":false,"error":null}',
        'data: {"delta":"","done":true,"error":null}',
    ]


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
    def _reject(schema):
        raise WorkbenchError(400, "invalid_output_schema", "bad schema")

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.chat.router.validate_output_schema", _reject),
    ):
        response = client.post(
            "/chat/stream", json={**_REQUEST, "output_schema": {"type": "object"}}
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_output_schema"
