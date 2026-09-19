from app.config import Settings, _platform_info, _total_ram_gb


def test_settings_defaults_to_no_api_key(monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.hf_api_key is None


def test_settings_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("HF_API_KEY", "hf_test_token")
    settings = Settings(_env_file=None)
    assert settings.hf_api_key == "hf_test_token"


def test_total_ram_gb_is_positive():
    assert _total_ram_gb() > 0


def test_platform_info_returns_known_system():
    system, machine = _platform_info()
    assert system in {"darwin", "linux", "windows"}
    assert machine  # non-empty string, e.g. "arm64" or "x86_64"


# get_hardware_info() is not tested yet — it depends on _detect_gpu(), which is not
# implemented (see the TODO in app/config.py). Add a test once that's filled in.
