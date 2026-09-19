import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.inference import registry
from app.inference.llama_cpp_backend import LlamaCppBackend
from app.inference.registry import get_backend
from app.models import DownloadedModelRecord

pytestmark = pytest.mark.ml

_test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch):
    monkeypatch.setattr(registry, "engine", _test_engine)
    SQLModel.metadata.create_all(_test_engine)
    yield
    SQLModel.metadata.drop_all(_test_engine)


def _seed(repo_id: str, quant: str | None, local_path: str) -> None:
    with Session(_test_engine) as session:
        session.add(
            DownloadedModelRecord(
                repo_id=repo_id,
                backend="gguf",
                quant=quant,
                local_path=local_path,
                size_bytes=1024,
            )
        )
        session.commit()


def test_get_backend_gguf_resolves_the_downloaded_file():
    _seed("org/model", "model.Q4_K_M.gguf", "/tmp/model.gguf")

    backend = get_backend("gguf", "org/model", hf_api_key=None)

    assert isinstance(backend, LlamaCppBackend)
    assert backend._model_path == "/tmp/model.gguf"


def test_get_backend_gguf_with_several_quants_resolves_an_explicit_filename():
    _seed("org/model", "a.gguf", "/tmp/a.gguf")
    _seed("org/model", "b.gguf", "/tmp/b.gguf")

    backend = get_backend("gguf", "org/model:b.gguf", hf_api_key=None)

    assert isinstance(backend, LlamaCppBackend)
    assert backend._model_path == "/tmp/b.gguf"
