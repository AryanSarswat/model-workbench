import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.errors import WorkbenchError
from app.inference import registry
from app.inference.hf_api_backend import HFInferenceAPIBackend
from app.inference.llama_cpp_backend import LlamaCppBackend
from app.inference.registry import get_backend
from app.inference.transformers_backend import TransformersBackend
from app.models import DownloadedModelRecord

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch):
    monkeypatch.setattr(registry, "engine", _test_engine)
    SQLModel.metadata.create_all(_test_engine)
    yield
    SQLModel.metadata.drop_all(_test_engine)


def _seed(
    repo_id: str, quant: str | None, local_path: str, backend: str = "gguf"
) -> None:
    with Session(_test_engine) as session:
        session.add(
            DownloadedModelRecord(
                repo_id=repo_id,
                backend=backend,
                quant=quant,
                local_path=local_path,
                size_bytes=1024,
            )
        )
        session.commit()


def test_get_backend_api_returns_hf_inference_api_backend():
    backend = get_backend("api", "some/model", hf_api_key="fake-key")

    assert isinstance(backend, HFInferenceAPIBackend)


def test_get_backend_api_without_key_raises_missing_hf_api_key():
    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("api", "some/model", hf_api_key=None)

    assert exc_info.value.code == "missing_hf_api_key"


def test_get_backend_unknown_name_raises_backend_not_supported():
    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("nope", "some/model", hf_api_key="fake-key")

    assert exc_info.value.code == "backend_not_supported"


def test_get_backend_gguf_resolves_the_downloaded_file():
    _seed("org/model", "model.Q4_K_M.gguf", "/tmp/model.gguf")

    backend = get_backend("gguf", "org/model", hf_api_key=None)

    assert isinstance(backend, LlamaCppBackend)
    assert backend._model_path == "/tmp/model.gguf"


def test_get_backend_gguf_without_download_raises_local_model_not_found():
    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("gguf", "org/missing", hf_api_key=None)

    assert exc_info.value.code == "local_model_not_found"
    assert exc_info.value.status_code == 404


def test_get_backend_gguf_with_several_quants_needs_an_explicit_filename():
    _seed("org/model", "a.gguf", "/tmp/a.gguf")
    _seed("org/model", "b.gguf", "/tmp/b.gguf")

    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("gguf", "org/model", hf_api_key=None)

    assert exc_info.value.code == "ambiguous_local_model"

    backend = get_backend("gguf", "org/model:b.gguf", hf_api_key=None)

    assert isinstance(backend, LlamaCppBackend)
    assert backend._model_path == "/tmp/b.gguf"


def test_get_backend_transformers_resolves_the_snapshot_dir():
    _seed("org/model", None, "/tmp/snapshot", backend="transformers")

    backend = get_backend("transformers", "org/model", hf_api_key=None)

    assert isinstance(backend, TransformersBackend)
    assert backend._snapshot_dir == "/tmp/snapshot"


def test_get_backend_transformers_without_download_raises_local_model_not_found():
    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("transformers", "org/missing", hf_api_key=None)

    assert exc_info.value.code == "local_model_not_found"
    assert exc_info.value.status_code == 404
