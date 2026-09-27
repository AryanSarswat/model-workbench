from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_tools_returns_every_registered_spec():
    response = client.get("/tools")

    assert response.status_code == 200
    assert {tool["name"] for tool in response.json()} == {"calculator", "web_fetch", "web_search"}


def test_reload_tools_returns_count():
    response = client.post("/tools/reload")

    assert response.status_code == 200
    assert response.json() == {"count": 3}
