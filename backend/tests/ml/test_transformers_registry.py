import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.errors import WorkbenchError
from app.inference import registry
from app.inference.registry import get_backend
from app.inference.transformers_backend import TransformersBackend
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


def _seed(repo_id: str, local_path: str) -> None:
    with Session(_test_engine) as session:
        session.add(
            DownloadedModelRecord(
                repo_id=repo_id,
                backend="transformers",
                quant=None,
                local_path=local_path,
                size_bytes=1024,
            )
        )
        session.commit()


def test_get_backend_transformers_resolves_the_snapshot_dir():
    _seed("org/model", "/tmp/snapshot")

    backend = get_backend("transformers", "org/model", hf_api_key=None)

    assert isinstance(backend, TransformersBackend)
    assert backend._snapshot_dir == "/tmp/snapshot"


def test_get_backend_transformers_without_download_raises_local_model_not_found():
    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("transformers", "org/missing", hf_api_key=None)

    assert exc_info.value.code == "local_model_not_found"
    assert exc_info.value.status_code == 404
