"""Model-feasibility estimate: will this model actually fit on this machine?

Two estimation paths, matching docs/architecture.md §8:
- A specific GGUF file (`quant`): estimate from that file's size.
- No `quant`: estimate from parameter_count x bytes-per-dtype (safetensors metadata).

Both get the same rough overhead factor for context/KV-cache memory beyond raw weights --
this is a heuristic, not a precise calculation, so one shared constant is deliberately
simpler than inventing separate numbers for each path without real data to justify them.
"""

from __future__ import annotations

from typing import Literal

from app.config import get_hardware_info
from app.discovery.hf_client import get_model_detail
from app.discovery.schemas import FeasibilityResult
from app.errors import WorkbenchError

_OVERHEAD_FACTOR = 1.2  # rough allowance for KV cache / activation memory beyond raw weights

_BYTES_PER_DTYPE: dict[str, int] = {
    "F64": 8,
    "F32": 4,
    "F16": 2,
    "BF16": 2,
    "I64": 8,
    "I32": 4,
    "I16": 2,
    "I8": 1,
    "U8": 1,
    "BOOL": 1,
}
_DEFAULT_BYTES_PER_PARAM = 4  # unknown dtype: assume F32 -- overestimating is the safe direction


def _bytes_per_param(dtype: str | None) -> int:
    if dtype is None:
        return _DEFAULT_BYTES_PER_PARAM
    return _BYTES_PER_DTYPE.get(dtype.upper(), _DEFAULT_BYTES_PER_PARAM)


def _verdict(
    estimated_gb: float, available_gb: float
) -> Literal["comfortable", "tight", "wont_fit"]:
    if estimated_gb < available_gb * 0.7:
        return "comfortable"
    if estimated_gb < available_gb * 0.95:
        return "tight"
    return "wont_fit"


def estimate_feasibility(model_id: str, quant: str | None = None) -> FeasibilityResult:
    detail = get_model_detail(model_id)  # reuses discovery's 404/502 handling as-is

    if quant is not None:
        matching_file = next((f for f in detail.gguf_files if f.filename == quant), None)
        if matching_file is None:
            raise WorkbenchError(
                status_code=404,
                code="gguf_file_not_found",
                message=f"'{quant}' is not a GGUF file in {model_id}.",
                details={"available_quants": [f.filename for f in detail.gguf_files]},
            )
        estimated_bytes = matching_file.size_bytes * _OVERHEAD_FACTOR
    else:
        if detail.parameter_count is None:
            raise WorkbenchError(
                status_code=422,
                code="feasibility_unknown",
                message=(
                    f"Can't estimate memory for {model_id}: no parameter metadata available "
                    "and no `quant` file specified."
                ),
            )
        bytes_per_param = _bytes_per_param(detail.dtype)
        estimated_bytes = detail.parameter_count * bytes_per_param * _OVERHEAD_FACTOR

    estimated_gb = round(estimated_bytes / (1024**3), 2)
    available_gb = get_hardware_info().usable_memory_gb
    verdict = _verdict(estimated_gb, available_gb)

    reason = f"~{estimated_gb}GB needed, {available_gb}GB available"
    if verdict == "wont_fit":
        reason += " -- will likely fail or swap heavily."
    elif verdict == "tight":
        reason += " -- should run, but leaves little headroom."
    else:
        reason += " -- should run comfortably."

    return FeasibilityResult(
        verdict=verdict,
        estimated_memory_gb=estimated_gb,
        available_memory_gb=available_gb,
        reason=reason,
    )
