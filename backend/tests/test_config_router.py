import pytest
from fastapi.testclient import TestClient

from app.config import GPUInfo, HardwareInfo
from app.main import app

client = TestClient(app)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """Point settings at a tmp .env so tests never read or write the real backend/.env."""
    monkeypatch.delenv("HF_API_KEY", raising=False)
    path = tmp_path / ".env"
    monkeypatch.setattr("app.config.ENV_FILE", str(path))
    return path


def test_hardware_reports_usable_memory_for_the_feasibility_check(monkeypatch):
    hardware = HardwareInfo(
        platform="linux",
        arch="x86_64",
        total_ram_gb=64.0,
        gpu=GPUInfo(kind="nvidia", name="RTX 4090", vram_gb=24.0),
    )
    monkeypatch.setattr("app.api_config.router.get_hardware_info", lambda: hardware)

    body = client.get("/config/hardware").json()

    assert body["gpu"]["name"] == "RTX 4090"
    assert body["usable_memory_gb"] == 24.0  # VRAM, not system RAM


def test_setting_the_key_is_visible_on_the_next_request_without_a_restart(env_file):
    assert client.get("/config/hf-api-key").json() == {"is_set": False}

    response = client.post("/config/hf-api-key", json={"api_key": "hf_abc"})

    assert response.json() == {"is_set": True}
    assert client.get("/config/hf-api-key").json() == {"is_set": True}
    assert "hf_abc" not in client.get("/config/hf-api-key").text


def test_setting_the_key_replaces_the_old_one_and_keeps_other_lines(env_file):
    env_file.write_text("OTHER_VAR=1\nHF_API_KEY=old\n")

    client.post("/config/hf-api-key", json={"api_key": "new"})

    assert env_file.read_text() == "OTHER_VAR=1\nHF_API_KEY=new\n"


def test_rejects_blank_or_multiline_keys_without_touching_the_file(env_file):
    for bad in ["   ", "hf_abc\nEVIL=1"]:
        response = client.post("/config/hf-api-key", json={"api_key": bad})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_api_key"
    assert not env_file.exists()
