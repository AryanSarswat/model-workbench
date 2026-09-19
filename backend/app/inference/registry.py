"""Maps a chat request's (`backend`, `model_id`) to a concrete InferenceBackend. The chat
router (and later the eval engine) call this instead of importing a specific backend
class -- adding transformers later means adding one branch here, not touching every call
site that runs a chat.

Local-model resolution happens here (not inside the stream) so an undownloaded or
ambiguous model_id raises before streaming starts and surfaces as a proper HTTP error
rather than a mid-stream failure.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.db import engine
from app.errors import WorkbenchError
from app.inference.base import InferenceBackend
from app.inference.hf_api_backend import HFInferenceAPIBackend
from app.inference.llama_cpp_backend import LlamaCppBackend
from app.models import DownloadedModelRecord


def get_backend(name: str, model_id: str, hf_api_key: str | None) -> InferenceBackend:
    if name == "api":
        if not hf_api_key:
            raise WorkbenchError(
                status_code=400,
                code="missing_hf_api_key",
                message="HF_API_KEY is not configured -- set it in backend/.env.",
            )
        return HFInferenceAPIBackend(hf_api_key)

    if name == "gguf":
        return LlamaCppBackend(_resolve_gguf_path(model_id))

    raise WorkbenchError(
        status_code=400,
        code="backend_not_supported",
        message=f"Backend '{name}' is not yet supported.",
    )


def _resolve_gguf_path(model_id: str) -> str:
    """model_id is a downloaded repo_id, or "repo_id:filename" to pick one quant when
    several are on disk. Colon works as the separator because it appears in neither HF
    repo ids nor GGUF filenames."""
    repo_id, _, filename = model_id.partition(":")
    with Session(engine) as session:
        statement = select(DownloadedModelRecord).where(
            DownloadedModelRecord.repo_id == repo_id,
            DownloadedModelRecord.backend == "gguf",
        )
        if filename:
            statement = statement.where(DownloadedModelRecord.quant == filename)
        records = list(session.exec(statement).all())

    if not records:
        raise WorkbenchError(
            status_code=404,
            code="local_model_not_found",
            message=f"No downloaded GGUF model matches '{model_id}' -- download it first.",
        )
    if len(records) > 1:
        available = sorted(r.quant for r in records if r.quant)
        raise WorkbenchError(
            status_code=400,
            code="ambiguous_local_model",
            message=f"Multiple GGUF quants of '{repo_id}' are downloaded -- pick one.",
            details={"available": available, "hint": "use 'repo_id:filename' as model_id"},
        )
    return records[0].local_path
