import subprocess
from unittest.mock import patch

from app.config import GPUInfo, _detect_gpu, _detect_nvidia_gpu, get_hardware_info


def test_detect_nvidia_gpu_returns_none_when_nvidia_smi_missing():
    with patch("app.config.subprocess.run", side_effect=FileNotFoundError):
        assert _detect_nvidia_gpu() is None


def test_detect_nvidia_gpu_parses_name_and_vram():
    fake_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="NVIDIA GeForce RTX 4090, 24564\n"
    )
    with patch("app.config.subprocess.run", return_value=fake_result):
        gpu = _detect_nvidia_gpu()
    assert gpu == GPUInfo(kind="nvidia", name="NVIDIA GeForce RTX 4090", vram_gb=24.0)


def test_detect_gpu_returns_apple_silicon_on_darwin_arm64():
    with patch("app.config._platform_info", return_value=("darwin", "arm64")):
        gpu = _detect_gpu()
    assert gpu == GPUInfo(kind="apple_silicon", vram_gb=None)


def test_detect_gpu_falls_back_to_none_without_nvidia_or_apple_silicon():
    with (
        patch("app.config._platform_info", return_value=("linux", "x86_64")),
        patch("app.config._detect_nvidia_gpu", return_value=None),
    ):
        gpu = _detect_gpu()
    assert gpu.kind == "none"


def test_get_hardware_info_assembles_real_hardware_snapshot():
    info = get_hardware_info()
    assert info.total_ram_gb > 0
    assert info.gpu.kind in {"apple_silicon", "nvidia", "none"}
