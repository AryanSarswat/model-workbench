from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_backends_reports_capabilities_and_local_backends_unavailable_without_the_extra(
    monkeypatch,
):
    """find_spec forced to None so this holds in full envs too, not just slim CI."""
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)

    response = client.get("/backends")

    assert response.status_code == 200
    assert response.json() == {
        "api": {
            "structured_output_mode": "prompt_retry",
            "native_tool_calling": False,
            "available": True,
        },
        "gguf": {
            "structured_output_mode": "grammar",
            "native_tool_calling": True,
            "available": False,
        },
        "transformers": {
            "structured_output_mode": "guided",
            "native_tool_calling": False,
            "available": False,
        },
    }


def test_list_backends_marks_local_backends_available_with_the_local_extra(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda name: SimpleNamespace(name=name))

    body = client.get("/backends").json()

    assert all(info["available"] for info in body.values())
