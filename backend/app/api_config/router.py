"""Config API: detected hardware and the HF API key (reported as set/unset, never echoed)."""

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app import config
from app.config import HardwareInfo, get_hardware_info, get_settings
from app.errors import WorkbenchError

router = APIRouter(prefix="/config", tags=["config"])


class SetApiKeyRequest(BaseModel):
    api_key: str


class ApiKeyStatus(BaseModel):
    is_set: bool


@router.get("/hardware")
def get_hardware() -> HardwareInfo:
    return get_hardware_info()


@router.get("/hf-api-key")
def get_hf_api_key_status() -> ApiKeyStatus:
    return ApiKeyStatus(is_set=bool(get_settings().hf_api_key))


@router.post("/hf-api-key")
def set_hf_api_key(req: SetApiKeyRequest) -> ApiKeyStatus:
    key = req.api_key.strip()
    # Any inner whitespace (esp. a newline) would let the value inject extra .env lines.
    if not key or any(ch.isspace() for ch in key):
        raise WorkbenchError(
            400, "invalid_api_key", "API key must be non-empty with no whitespace."
        )

    env_path = Path(config.ENV_FILE)
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    lines = [line for line in lines if not line.startswith("HF_API_KEY=")]
    lines.append(f"HF_API_KEY={key}")
    env_path.write_text("\n".join(lines) + "\n")
    return ApiKeyStatus(is_set=True)
