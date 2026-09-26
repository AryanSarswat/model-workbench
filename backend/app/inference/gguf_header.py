"""Read tensor types from a GGUF header, to explain a load llama.cpp rejects.

llama.cpp reports an unknown tensor type only in its (suppressed) log and raises
a generic "Failed to load model", so a file quantized for a fork (e.g. PrismML's
PQ2_0) looks corrupt. This scans the header with the stdlib; no tensor data is read.
Format: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO

# Fixed-size metadata value types -> byte width. 8 (string) and 9 (array) vary.
_FIXED_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_STRING, _ARRAY = 8, 9


def _read(f: BinaryIO, fmt: str) -> int:
    size = struct.calcsize(fmt)
    data = f.read(size)
    if len(data) != size:
        raise ValueError("truncated GGUF header")
    return struct.unpack(fmt, data)[0]


def _read_string(f: BinaryIO) -> str:
    length = _read(f, "<Q")
    return f.read(length).decode(errors="replace")


def _skip_value(f: BinaryIO, value_type: int) -> None:
    if value_type == _STRING:
        f.seek(_read(f, "<Q"), 1)
    elif value_type == _ARRAY:
        item_type = _read(f, "<I")
        count = _read(f, "<Q")
        if item_type in _FIXED_SIZES:
            f.seek(_FIXED_SIZES[item_type] * count, 1)
        else:
            for _ in range(count):
                _skip_value(f, item_type)
    elif value_type in _FIXED_SIZES:
        f.seek(_FIXED_SIZES[value_type], 1)
    else:
        raise ValueError(f"unknown GGUF metadata type {value_type}")


def find_unsupported_tensor(path: str | Path, type_count: int) -> tuple[str, int] | None:
    """The first tensor whose ggml type is >= type_count, as (name, type); None when
    every tensor type is in range. Raises ValueError on a file that isn't GGUF v2+."""
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("not a GGUF file")
        if _read(f, "<I") < 2:
            raise ValueError("GGUF v1 is not supported")
        tensor_count = _read(f, "<Q")
        kv_count = _read(f, "<Q")
        for _ in range(kv_count):
            f.seek(_read(f, "<Q"), 1)  # key
            _skip_value(f, _read(f, "<I"))
        for _ in range(tensor_count):
            name = _read_string(f)
            n_dims = _read(f, "<I")
            f.seek(8 * n_dims, 1)
            ggml_type = _read(f, "<I")
            f.seek(8, 1)  # data offset
            if ggml_type >= type_count:
                return name, ggml_type
    return None


def describe_unsupported(path: str | Path, type_count: int) -> str | None:
    """Why a llama.cpp build reading ggml types below type_count can't load this
    file; None when every tensor type is in range or the header can't be read."""
    try:
        unsupported = find_unsupported_tensor(path, type_count)
    except (OSError, ValueError):
        return None
    if unsupported is None:
        return None
    tensor, ggml_type = unsupported
    return (
        f"unsupported quantization: tensor '{tensor}' in {Path(path).name} uses "
        f"ggml type {ggml_type}, but this llama.cpp build reads types "
        f"0-{type_count - 1}. The file likely needs its publisher's "
        "llama.cpp fork; choose another quantization."
    )
