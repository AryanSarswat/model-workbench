"""App settings and hardware detection.

Hardware detection feeds the model-feasibility check (design doc §8): before downloading a
model, we compare its estimated memory footprint against what's actually available on this
machine.
"""

from __future__ import annotations

import platform
import subprocess

import psutil
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loaded from backend/.env (see .env.example). Never logged or persisted to the DB."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    hf_api_key: str | None = None


def get_settings() -> Settings:
    return Settings()


class GPUInfo(BaseModel):
    kind: str  # "apple_silicon" | "nvidia" | "none"
    name: str | None = None
    vram_gb: float | None = None  # None for apple_silicon (unified memory, use total_ram_gb)


class HardwareInfo(BaseModel):
    platform: str  # "darwin" | "linux" | "windows"
    arch: str  # e.g. "arm64", "x86_64"
    total_ram_gb: float
    gpu: GPUInfo


def _platform_info() -> tuple[str, str]:
    return platform.system().lower(), platform.machine().lower()


def _total_ram_gb() -> float:
    return round(psutil.virtual_memory().total / (1024**3), 1)


def _detect_nvidia_gpu() -> GPUInfo | None:
    """Returns GPUInfo if `nvidia-smi` reports a GPU, else None. No torch dependency."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    first_line = result.stdout.strip().splitlines()[0]
    name, vram_mib = (part.strip() for part in first_line.split(","))
    return GPUInfo(kind="nvidia", name=name, vram_gb=round(float(vram_mib) / 1024, 1))


def _detect_gpu() -> GPUInfo:
    system, machine = _platform_info()
    if system == "darwin" and machine == "arm64":
        # Unified memory — no separate VRAM figure; feasibility checks use total_ram_gb.
        return GPUInfo(kind="apple_silicon", vram_gb=None)

    nvidia_gpu = _detect_nvidia_gpu()
    if nvidia_gpu is not None:
        return nvidia_gpu

    return GPUInfo(kind="none")


def get_hardware_info() -> HardwareInfo:
    system, machine = _platform_info()
    return HardwareInfo(
        platform=system,
        arch=machine,
        total_ram_gb=_total_ram_gb(),
        gpu=_detect_gpu(),
    )
