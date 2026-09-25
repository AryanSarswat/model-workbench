"""Config API: hardware detection and settings (HF API key)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import ENV_FILE, HardwareInfo, get_hardware_info, get_settings
from app.errors import WorkbenchError

router = APIRouter(prefix="/config", tags=["config"])


class SetApiKeyRequest(BaseModel):
    api_key: str


class ApiKeyStatus(BaseModel):
    is_set: bool


@router.get("/hardware")
def get_hardware() -> HardwareInfo:
    """Return hardware info including usable_memory_gb (for model feasibility check)."""
    return get_hardware_info()


@router.get("/hf-api-key")
def check_hf_api_key() -> ApiKeyStatus:
    """Check if HF_API_KEY is configured."""
    settings = get_settings()
    return ApiKeyStatus(is_set=settings.hf_api_key is not None and len(settings.hf_api_key.strip()) > 0)


@router.post("/hf-api-key")
def set_hf_api_key(req: SetApiKeyRequest) -> ApiKeyStatus:
    """Set HF_API_KEY in .env file (replaces existing or creates new)."""
    if not req.api_key or not req.api_key.strip():
        raise WorkbenchError(400, "invalid_api_key", "API key cannot be empty or whitespace-only")

    env_path = Path(ENV_FILE)

    # Read existing lines
    existing_lines = []
    if env_path.exists():
        with open(env_path) as f:
            existing_lines = f.readlines()

    # Find and replace or append HF_API_KEY
    found = False
    new_lines = []
    for line in existing_lines:
        if line.startswith("HF_API_KEY="):
            new_lines.append(f"HF_API_KEY={req.api_key}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"HF_API_KEY={req.api_key}\n")

    # Write back
    with open(env_path, "w") as f:
        f.writelines(new_lines)

    return ApiKeyStatus(is_set=True)
