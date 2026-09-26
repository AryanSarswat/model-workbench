"""The GGUF header scan behind the "unsupported quantization" load error."""

from app.inference.gguf_header import find_unsupported_tensor
from tests.gguf_fixtures import write_gguf

# llama-cpp-python 0.3.35 knows ggml types 0..42.
TYPE_COUNT = 43


def test_reports_the_first_tensor_whose_type_this_llama_cpp_cannot_read(tmp_path):
    # PrismML's PQ2_0 files store weights as ggml type 142, which stock llama.cpp lacks.
    path = write_gguf(tmp_path / "m.gguf", {"token_embd.weight": 1, "output.weight": 142})

    assert find_unsupported_tensor(path, TYPE_COUNT) == ("output.weight", 142)


def test_returns_none_when_every_tensor_type_is_supported(tmp_path):
    path = write_gguf(tmp_path / "m.gguf", {"token_embd.weight": 1, "output.weight": 14})

    assert find_unsupported_tensor(path, TYPE_COUNT) is None
