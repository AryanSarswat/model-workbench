from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.db import get_session
from app.inference.schemas import ChatChunk
from app.main import app
from app.models import ChatMessageRecord, ChatSession

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _override_get_session():
    with Session(_test_engine) as session:
        yield session


client = TestClient(app)

_REQUEST = {"model_id": "some/model", "messages": [{"role": "user", "content": "hi"}]}


@pytest.fixture(autouse=True)
def _reset_db():
    # test_downloads.py sets the same app-global override at import time; save and
    # restore it so these tests run against their own engine without breaking others.
    SQLModel.metadata.create_all(_test_engine)
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override_get_session
    yield
    SQLModel.metadata.drop_all(_test_engine)
    if previous is not None:
        app.dependency_overrides[get_session] = previous
    else:
        app.dependency_overrides.pop(get_session, None)


def _seed_session() -> int:
    with Session(_test_engine) as session:
        chat_session = ChatSession()
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)
        return chat_session.id


def _seed_message(session_id: int, role: str, content: str, sequence: int) -> None:
    with Session(_test_engine) as session:
        session.add(
            ChatMessageRecord(
                session_id=session_id, role=role, content=content, sequence=sequence
            )
        )
        session.commit()


def _messages_in_db(session_id: int) -> list[ChatMessageRecord]:
    with Session(_test_engine) as session:
        return list(
            session.exec(
                select(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
                .order_by(ChatMessageRecord.sequence)
            ).all()
        )


def _stream(**overrides):
    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta="Hel")
        yield ChatChunk(delta="lo")
        yield ChatChunk(done=True)

    body = {**_REQUEST, **overrides}
    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        return client.post("/chat/stream", json=body)


def test_create_session_returns_id_and_lists_newest_first():
    first = client.post("/chat/sessions")
    second = client.post("/chat/sessions")

    assert first.status_code == 201
    assert second.status_code == 201
    assert set(first.json()) == {"id", "created_at"}
    assert first.json()["id"] != second.json()["id"]

    listed = client.get("/chat/sessions").json()
    assert [s["id"] for s in listed] == [second.json()["id"], first.json()["id"]]


def test_stream_with_session_persists_user_and_assistant_round_trip():
    create_response = client.post("/chat/sessions")
    assert create_response.status_code == 201
    session_id = create_response.json()["id"]

    response = _stream(session_id=session_id)

    assert response.status_code == 200
    stored = [(m.role, m.content) for m in _messages_in_db(session_id)]
    assert stored == [("user", "hi"), ("assistant", "Hello")]


def test_stream_without_session_id_writes_nothing():
    session_id = _seed_session()

    response = _stream()

    assert response.status_code == 200
    assert _messages_in_db(session_id) == []


def test_stream_with_unknown_session_id_returns_404_before_streaming():
    entered_stream = []

    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        entered_stream.append(True)
        yield ChatChunk(done=True)

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        response = client.post("/chat/stream", json={**_REQUEST, "session_id": 9999})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_session_not_found"
    assert entered_stream == []


def test_stream_with_session_stores_only_the_new_user_turn():
    """The client resends full history, so the already-recorded turns must not duplicate."""
    session_id = _seed_session()
    _seed_message(session_id, "user", "hi", 1)
    _seed_message(session_id, "assistant", "Hello", 2)

    response = _stream(
        session_id=session_id,
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "again"},
        ],
    )

    assert response.status_code == 200
    stored = [(m.role, m.content) for m in _messages_in_db(session_id)]
    assert stored == [("user", "hi"), ("assistant", "Hello"), ("user", "again"), ("assistant", "Hello")]


def test_stream_error_persists_no_assistant_reply():
    session_id = _seed_session()

    async def fake_stream_chat(self, model_id, messages, tools=None, output_schema=None):
        yield ChatChunk(delta="partial")
        yield ChatChunk(error="boom")

    with (
        patch("app.chat.router.get_settings", return_value=Settings(hf_api_key="fake-key")),
        patch("app.inference.hf_api_backend.HFInferenceAPIBackend.stream_chat", fake_stream_chat),
    ):
        response = client.post("/chat/stream", json={**_REQUEST, "session_id": session_id})

    assert response.status_code == 200
    stored = [(m.role, m.content) for m in _messages_in_db(session_id)]
    assert stored == [("user", "hi")]


def test_get_session_returns_messages_in_sequence_order():
    session_id = _seed_session()
    _seed_message(session_id, "assistant", "second", 2)
    _seed_message(session_id, "user", "first", 1)

    response = client.get(f"/chat/sessions/{session_id}")

    assert response.status_code == 200
    assert [(m["role"], m["content"]) for m in response.json()["messages"]] == [
        ("user", "first"),
        ("assistant", "second"),
    ]


def test_get_missing_session_returns_404():
    response = client.get("/chat/sessions/9999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_session_not_found"


def test_delete_session_removes_messages_and_get_then_404s():
    session_id = _seed_session()
    _seed_message(session_id, "user", "hi", 1)

    response = client.delete(f"/chat/sessions/{session_id}")

    assert response.status_code == 204
    assert _messages_in_db(session_id) == []
    assert client.get(f"/chat/sessions/{session_id}").status_code == 404


def test_delete_missing_session_returns_404():
    response = client.delete("/chat/sessions/9999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "chat_session_not_found"
