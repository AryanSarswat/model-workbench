import pytest

from app.errors import WorkbenchError
from app.inference.hf_api_backend import HFInferenceAPIBackend
from app.inference.registry import get_backend


def test_get_backend_api_returns_hf_inference_api_backend():
    backend = get_backend("api", hf_api_key="fake-key")

    assert isinstance(backend, HFInferenceAPIBackend)


def test_get_backend_api_without_key_raises_missing_hf_api_key():
    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("api", hf_api_key=None)

    assert exc_info.value.code == "missing_hf_api_key"


def test_get_backend_unknown_name_raises_backend_not_supported():
    with pytest.raises(WorkbenchError) as exc_info:
        get_backend("gguf", hf_api_key="fake-key")

    assert exc_info.value.code == "backend_not_supported"
