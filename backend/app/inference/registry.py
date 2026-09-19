"""Maps a chat request's (`backend`, `model_id`) to a concrete InferenceBackend. The chat
router (and later the eval engine) call this instead of importing a specific backend
class -- adding a backend means adding one branch here, not touching every call site
that runs a chat.

Local-model resolution happens here (not inside the stream) so an undownloaded or
ambiguous model_id raises before streaming starts and surfaces as a proper HTTP error
rather than a mid-stream failure.

The local backends live behind the `local` extra (torch/llama.cpp) and are imported
lazily -- importing this module must never require them, so the app boots and the
application suite passes in a slim env without them. Resolution (pure DB) still runs
first, so undownloaded-model 404s stay slim-safe; only constructing the backend needs
the extra.
"""

from __future__ import annotations

import importlib.util

from sqlmodel import Session, select

from app.db import engine
from app.errors import WorkbenchError
from app.inference.base import InferenceBackend
from app.inference.hf_api_backend import HFInferenceAPIBackend
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
        path = _resolve_gguf_path(model_id)
        _require_local(name, "llama_cpp")
        from app.inference.llama_cpp_backend import LlamaCppBackend

        return LlamaCppBackend(path)

    if name == "transformers":
        snapshot_dir = _resolve_snapshot_dir(model_id)
        _require_local(name, "torch", "transformers")
        from app.inference.transformers_backend import TransformersBackend

        return TransformersBackend(snapshot_dir)

    raise WorkbenchError(
        status_code=400,
        code="backend_not_supported",
        message=f"Backend '{name}' is not yet supported.",
    )


def _require_local(backend: str, *modules: str) -> None:
    """Fail fast with a proper HTTP error when the `local` extra isn't installed.
    find_spec (not try/except around the import) so a genuine bug inside a backend
    module still surfaces as a real traceback instead of a misleading install hint."""
    missing = [m for m in modules if importlib.util.find_spec(m) is None]
    if missing:
        raise WorkbenchError(
            status_code=400,
            code="backend_not_available",
            message=(
                f"The '{backend}' backend needs the 'local' extra "
                f"(missing: {', '.join(missing)}) -- "
                "run 'cd backend && uv sync --extra local'."
            ),
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


def _resolve_snapshot_dir(model_id: str) -> str:
    """model_id is a downloaded repo_id -- snapshots have no quants, so unlike GGUF
    there is no `repo_id:filename` form. Re-downloads insert a fresh row pointing at
    the same snapshot dir, so the latest one wins deterministically."""
    with Session(engine) as session:
        statement = (
            select(DownloadedModelRecord)
            .where(
                DownloadedModelRecord.repo_id == model_id,
                DownloadedModelRecord.backend == "transformers",
            )
            .order_by(DownloadedModelRecord.downloaded_at.desc())
        )
        record = session.exec(statement).first()

    if record is None:
        raise WorkbenchError(
            status_code=404,
            code="local_model_not_found",
            message=f"No downloaded transformers snapshot matches '{model_id}' -- download it first.",
        )
    return record.local_path
