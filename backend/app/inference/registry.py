"""Maps a chat request's `backend` field to a concrete InferenceBackend. The chat router
(and later the eval engine) call this instead of importing a specific backend class --
adding llama.cpp/transformers later means adding one branch here, not touching every call
site that runs a chat.
"""

from __future__ import annotations

from app.errors import WorkbenchError
from app.inference.base import InferenceBackend
from app.inference.hf_api_backend import HFInferenceAPIBackend


def get_backend(name: str, hf_api_key: str | None) -> InferenceBackend:
    if name == "api":
        if not hf_api_key:
            raise WorkbenchError(
                status_code=400,
                code="missing_hf_api_key",
                message="HF_API_KEY is not configured -- set it in backend/.env.",
            )
        return HFInferenceAPIBackend(hf_api_key)

    raise WorkbenchError(
        status_code=400,
        code="backend_not_supported",
        message=f"Backend '{name}' is not yet supported.",
    )
