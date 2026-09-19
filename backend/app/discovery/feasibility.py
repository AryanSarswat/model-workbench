"""Model-feasibility estimate: will this model actually fit on this machine?

Two estimation methods, matching docs/architecture.md §8:
- Each GGUF file: estimate from that file's size.
- The transformers path: estimate from parameter_count x bytes-per-dtype (safetensors
  metadata).

Both get the same rough overhead factor for context/KV-cache memory beyond raw weights --
this is a heuristic, not a precise calculation, so one shared constant is deliberately
simpler than inventing separate numbers for each path without real data to justify them.

A model page commonly has many GGUF quants (a dozen+ isn't unusual), so `estimate_feasibility`
fetches model detail once and evaluates every option against it in one pass, rather than
making the caller loop and re-fetch per quant. Pass `quant` to narrow the result down to one
specific file (e.g. right before confirming a download).
"""

from __future__ import annotations

from app.config import get_hardware_info
from app.discovery.hf_client import get_model_detail
from app.discovery.schemas import FeasibilityOption, FeasibilityReport, GgufFile, ModelDetail
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

_COMFORTABLE_THRESHOLD = 0.7  # estimated_gb below this fraction of available_gb: "comfortable"
_TIGHT_THRESHOLD = 0.95  # below this fraction: "tight"; at or above: "wont_fit"


def _bytes_per_param(dtype: str | None) -> int:
    if dtype is None:
        return _DEFAULT_BYTES_PER_PARAM
    return _BYTES_PER_DTYPE.get(dtype.upper(), _DEFAULT_BYTES_PER_PARAM)


def _build_option(label: str, estimated_bytes: float, available_gb: float) -> FeasibilityOption:
    estimated_gb = round(estimated_bytes / (1024**3), 2)
    if estimated_gb < available_gb * _COMFORTABLE_THRESHOLD:
        verdict = "comfortable"
        reason_suffix = "should run comfortably."
    elif estimated_gb < available_gb * _TIGHT_THRESHOLD:
        verdict = "tight"
        reason_suffix = "should run, but leaves little headroom."
    else:
        verdict = "wont_fit"
        reason_suffix = "will likely fail or swap heavily."

    reason = f"~{estimated_gb}GB needed, {available_gb}GB available -- {reason_suffix}"
    return FeasibilityOption(
        label=label, verdict=verdict, estimated_memory_gb=estimated_gb, reason=reason
    )


def _gguf_option(file: GgufFile, available_gb: float) -> FeasibilityOption:
    return _build_option(file.filename, file.size_bytes * _OVERHEAD_FACTOR, available_gb)


def _transformers_option(detail: ModelDetail, available_gb: float) -> FeasibilityOption | None:
    if detail.parameter_count is None:
        return None
    estimated_bytes = detail.parameter_count * _bytes_per_param(detail.dtype) * _OVERHEAD_FACTOR
    label = f"transformers ({detail.dtype or 'unknown dtype'})"
    return _build_option(label, estimated_bytes, available_gb)


def estimate_feasibility(model_id: str, quant: str | None = None) -> FeasibilityReport:
    detail = get_model_detail(model_id)  # one fetch, reused for every option below
    available_gb = get_hardware_info().usable_memory_gb

    if quant is not None:
        matching_file = next((f for f in detail.gguf_files if f.filename == quant), None)
        if matching_file is None:
            raise WorkbenchError(
                status_code=404,
                code="gguf_file_not_found",
                message=f"'{quant}' is not a GGUF file in {model_id}.",
                details={"available_quants": [f.filename for f in detail.gguf_files]},
            )
        options = [_gguf_option(matching_file, available_gb)]
    else:
        options = [_gguf_option(f, available_gb) for f in detail.gguf_files]
        transformers_option = _transformers_option(detail, available_gb)
        if transformers_option is not None:
            options.append(transformers_option)

        if not options:
            raise WorkbenchError(
                status_code=422,
                code="feasibility_unknown",
                message=(
                    f"Can't estimate memory for {model_id}: no GGUF files and no "
                    "parameter metadata available."
                ),
            )

    return FeasibilityReport(available_memory_gb=available_gb, options=options)
