"""App settings and hardware detection.

Hardware detection feeds the model-feasibility check (design doc §8): before downloading a
model, we compare its estimated memory footprint against what's actually available on this
machine.
"""

from __future__ import annotations

import platform

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


def _detect_gpu() -> GPUInfo:
    # TODO(human): detect available GPU acceleration and return a GPUInfo.
    #
    # This feeds the feasibility check in design doc §8 ("comfortable / tight / wont_fit"),
    # so it needs to distinguish:
    #   - Apple Silicon (darwin + arm64): unified memory, so there's no separate VRAM figure —
    #     return GPUInfo(kind="apple_silicon", vram_gb=None) and the feasibility checker will
    #     use total_ram_gb instead.
    #   - NVIDIA GPU present: return GPUInfo(kind="nvidia", name=..., vram_gb=...).
    #   - Nothing usable: return GPUInfo(kind="none").
    #
    # Constraint: keep this dependency-light. We deliberately did NOT add torch to this
    # module's dependencies just to ask "is there a GPU" — that's a huge install for a
    # yes/no question. Consider subprocess-ing `nvidia-smi` (already on the PATH on any
    # machine with an NVIDIA driver installed) for the NVIDIA case, e.g.:
    #   nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
    # and platform.system()/platform.machine() (see _platform_info above) for Apple Silicon.
    # Handle the "nvidia-smi not found" case (FileNotFoundError) as kind="none" on non-NVIDIA
    # machines rather than raising.
    raise NotImplementedError


def get_hardware_info() -> HardwareInfo:
    system, machine = _platform_info()
    return HardwareInfo(
        platform=system,
        arch=machine,
        total_ram_gb=_total_ram_gb(),
        gpu=_detect_gpu(),
    )
