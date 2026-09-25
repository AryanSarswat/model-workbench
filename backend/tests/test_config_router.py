from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_hardware_info_returns_expected_shape(monkeypatch):
    mock_hardware = {
        "platform": "darwin",
        "arch": "arm64",
        "total_ram_gb": 24.0,
        "gpu": {"kind": "apple_silicon", "name": None, "vram_gb": None},
    }
    monkeypatch.setattr("app.api_config.router.get_hardware_info", lambda: type("HW", (), mock_hardware)())

    response = client.get("/config/hardware")

    assert response.status_code == 200
    data = response.json()
    assert data["platform"] == "darwin"
    assert data["arch"] == "arm64"
    assert data["total_ram_gb"] == 24.0
    assert data["gpu"]["kind"] == "apple_silicon"
    assert "usable_memory_gb" in data
    assert data["usable_memory_gb"] == 24.0


def test_get_hf_api_key_reports_not_set_when_missing(monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.setattr("app.api_config.router.ENV_FILE", "/tmp/test_missing.env")

    response = client.get("/config/hf-api-key")

    assert response.status_code == 200
    assert response.json() == {"is_set": False}


def test_post_hf_api_key_sets_and_get_reports_set(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr("app.api_config.router.ENV_FILE", str(env_file))

    response = client.post("/config/hf-api-key", json={"api_key": "hf_test_key_12345"})

    assert response.status_code == 200
    assert response.json() == {"is_set": True}

    # Verify file was written
    content = env_file.read_text()
    assert "HF_API_KEY=hf_test_key_12345" in content

    # Verify GET now reports set (need to reload settings, so monkeypatch it)
    monkeypatch.setattr("app.api_config.router.get_settings", lambda: type("S", (), {"hf_api_key": "hf_test_key_12345"})())
    response = client.get("/config/hf-api-key")
    assert response.status_code == 200
    assert response.json() == {"is_set": True}


def test_post_hf_api_key_preserves_other_env_lines_and_replaces_existing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_VAR=value1\nHF_API_KEY=old_key\nANOTHER_VAR=value2\n")
    monkeypatch.setattr("app.api_config.router.ENV_FILE", str(env_file))

    response = client.post("/config/hf-api-key", json={"api_key": "hf_new_key"})

    assert response.status_code == 200

    content = env_file.read_text()
    assert "OTHER_VAR=value1" in content
    assert "ANOTHER_VAR=value2" in content
    assert "HF_API_KEY=hf_new_key" in content
    assert "HF_API_KEY=old_key" not in content


def test_post_hf_api_key_rejects_empty_key(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr("app.api_config.router.ENV_FILE", str(env_file))

    response = client.post("/config/hf-api-key", json={"api_key": ""})

    assert response.status_code == 400
    error = response.json()
    assert "error" in error
    assert error["error"]["code"] == "invalid_api_key"
    assert "empty" in error["error"]["message"].lower()


def test_post_hf_api_key_rejects_whitespace_only_key(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    monkeypatch.setattr("app.api_config.router.ENV_FILE", str(env_file))

    response = client.post("/config/hf-api-key", json={"api_key": "   \t\n"})

    assert response.status_code == 400
    error = response.json()
    assert "error" in error
    assert error["error"]["code"] == "invalid_api_key"
