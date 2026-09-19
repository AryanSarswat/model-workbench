from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import GPUInfo, HardwareInfo
from app.discovery.feasibility import estimate_feasibility
from app.discovery.schemas import FeasibilityResult, GgufFile, ModelDetail
from app.errors import WorkbenchError
from app.main import app

client = TestClient(app)

_HARDWARE_16GB = HardwareInfo(
    platform="linux", arch="x86_64", total_ram_gb=16.0, gpu=GPUInfo(kind="none")
)


def _detail(**overrides) -> ModelDetail:
    defaults = {"id": "meta-llama/Llama-3-8B"}
    return ModelDetail(**{**defaults, **overrides})


def test_gguf_quant_estimates_from_file_size():
    detail = _detail(gguf_files=[GgufFile(filename="model.Q4_K_M.gguf", size_bytes=5 * 1024**3)])
    with (
        patch("app.discovery.feasibility.get_model_detail", return_value=detail),
        patch("app.discovery.feasibility.get_hardware_info", return_value=_HARDWARE_16GB),
    ):
        result = estimate_feasibility("meta-llama/Llama-3-8B", quant="model.Q4_K_M.gguf")
    assert result.estimated_memory_gb == 6.0  # 5GB * 1.2 overhead
    assert result.verdict == "comfortable"  # 6 < 16 * 0.7


def test_unknown_quant_raises_404_with_available_options():
    detail = _detail(gguf_files=[GgufFile(filename="model.Q4_K_M.gguf", size_bytes=1024)])
    with (
        patch("app.discovery.feasibility.get_model_detail", return_value=detail),
        pytest.raises(WorkbenchError) as exc_info,
    ):
        estimate_feasibility("meta-llama/Llama-3-8B", quant="nonexistent.gguf")
    assert exc_info.value.status_code == 404
    assert exc_info.value.details["available_quants"] == ["model.Q4_K_M.gguf"]


def test_no_quant_estimates_from_parameter_count_and_dtype():
    detail = _detail(parameter_count=7_000_000_000, dtype="BF16")
    with (
        patch("app.discovery.feasibility.get_model_detail", return_value=detail),
        patch("app.discovery.feasibility.get_hardware_info", return_value=_HARDWARE_16GB),
    ):
        result = estimate_feasibility("meta-llama/Llama-3-8B")
    # 7B params * 2 bytes (BF16) * 1.2 overhead = ~15.65GB
    assert result.estimated_memory_gb == pytest.approx(15.65, abs=0.01)
    assert result.verdict == "wont_fit"  # 15.65 > 16 * 0.95


def test_tight_verdict_when_close_to_available_memory():
    # 7B params * 2 bytes (BF16) * 1.2 = ~15.65GB against 20GB available: 0.7*20=14, 0.95*20=19
    detail = _detail(parameter_count=7_000_000_000, dtype="BF16")
    hardware_20gb = HardwareInfo(
        platform="linux", arch="x86_64", total_ram_gb=20.0, gpu=GPUInfo(kind="none")
    )
    with (
        patch("app.discovery.feasibility.get_model_detail", return_value=detail),
        patch("app.discovery.feasibility.get_hardware_info", return_value=hardware_20gb),
    ):
        result = estimate_feasibility("meta-llama/Llama-3-8B")
    assert result.verdict == "tight"


def test_unknown_dtype_falls_back_to_4_bytes_per_param():
    detail = _detail(parameter_count=1_000_000_000, dtype="some_future_dtype")
    with (
        patch("app.discovery.feasibility.get_model_detail", return_value=detail),
        patch("app.discovery.feasibility.get_hardware_info", return_value=_HARDWARE_16GB),
    ):
        result = estimate_feasibility("meta-llama/Llama-3-8B")
    # 1B params * 4 bytes (fallback) * 1.2 overhead = ~4.47GB
    assert result.estimated_memory_gb == pytest.approx(4.47, abs=0.01)


def test_no_quant_and_no_parameter_count_raises_422():
    detail = _detail()  # no gguf_files, no parameter_count
    with (
        patch("app.discovery.feasibility.get_model_detail", return_value=detail),
        pytest.raises(WorkbenchError) as exc_info,
    ):
        estimate_feasibility("meta-llama/Llama-3-8B")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "feasibility_unknown"


def test_feasibility_endpoint_returns_verdict():
    with patch("app.discovery.router.estimate_feasibility") as mock_estimate:
        mock_estimate.return_value = FeasibilityResult(
            verdict="comfortable", estimated_memory_gb=4.0, available_memory_gb=16.0, reason="ok"
        )
        response = client.get("/models/meta-llama/Llama-3-8B/feasibility?quant=model.gguf")
    assert response.status_code == 200
    assert response.json()["verdict"] == "comfortable"
    mock_estimate.assert_called_once_with("meta-llama/Llama-3-8B", quant="model.gguf")


def test_feasibility_route_is_not_swallowed_by_model_detail_catch_all():
    """/models/{model_id:path}/feasibility must be tried before /models/{model_id:path},
    or the detail route would swallow it with model_id="meta-llama/Llama-3-8B/feasibility"."""
    with (
        patch("app.discovery.router.estimate_feasibility") as mock_feasibility,
        patch("app.discovery.router.get_model_detail") as mock_detail,
    ):
        mock_feasibility.return_value = FeasibilityResult(
            verdict="comfortable", estimated_memory_gb=1.0, available_memory_gb=16.0, reason="ok"
        )
        response = client.get("/models/meta-llama/Llama-3-8B/feasibility")
    assert response.status_code == 200
    mock_feasibility.assert_called_once()
    mock_detail.assert_not_called()


@pytest.mark.network
def test_feasibility_endpoint_against_real_hf_hub():
    response = client.get("/models/Qwen/Qwen2.5-0.5B-Instruct/feasibility")
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] in {"comfortable", "tight", "wont_fit"}
    assert body["estimated_memory_gb"] > 0
