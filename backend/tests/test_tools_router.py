from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_tools_returns_both_specs():
    response = client.get("/tools")

    assert response.status_code == 200
    assert {tool["name"] for tool in response.json()} == {"calculator", "web_fetch"}


def test_reload_tools_returns_count():
    response = client.post("/tools/reload")

    assert response.status_code == 200
    assert response.json() == {"count": 2}
