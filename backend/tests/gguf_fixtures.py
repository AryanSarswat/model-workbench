"""Writes minimal GGUF files (header + metadata + tensor infos, no tensor data) for tests."""

from __future__ import annotations

import struct
from pathlib import Path

_STRING, _ARRAY, _UINT32 = 8, 9, 4


def _string(value: str) -> bytes:
    raw = value.encode()
    return struct.pack("<Q", len(raw)) + raw


def write_gguf(path: Path, tensor_types: dict[str, int]) -> Path:
    """A GGUF v3 file with a string-array and a uint32 metadata entry (so readers
    must skip variable-length values) and one 1-D tensor info per name -> ggml type."""
    kvs = (
        _string("tokenizer.ggml.tokens")
        + struct.pack("<IIQ", _ARRAY, _STRING, 2)
        + _string("hello")
        + _string("world")
        + _string("general.alignment")
        + struct.pack("<II", _UINT32, 32)
    )
    tensors = b"".join(
        _string(name) + struct.pack("<IQIQ", 1, 8, ggml_type, 0)
        for name, ggml_type in tensor_types.items()
    )
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, len(tensor_types), 2) + kvs + tensors)
    return path
