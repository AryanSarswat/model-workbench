import type { BackendName, DownloadedModelRecord } from '../../api/types'

export interface ModelOption {
  modelId: string // value to send as ChatRequest.model_id
  label: string
}

// gguf model_id is the bare repo_id when only one quant of that repo is downloaded,
// else "repo_id:quant" -- mirrors _resolve_gguf_path in
// backend/app/inference/registry.py.
export function ggufModelOptions(records: DownloadedModelRecord[]): ModelOption[] {
  const countByRepo = new Map<string, number>()
  for (const record of records) countByRepo.set(record.repo_id, (countByRepo.get(record.repo_id) ?? 0) + 1)
  return records.map((record) => {
    const ambiguous = (countByRepo.get(record.repo_id) ?? 0) > 1
    const modelId = ambiguous ? `${record.repo_id}:${record.quant}` : record.repo_id
    const label = ambiguous ? `${record.repo_id} (${record.quant})` : record.repo_id
    return { modelId, label }
  })
}

// transformers model_id is always the bare repo_id -- dedupe repeated downloads of the
// same repo (the registry resolves to the most recently downloaded row).
export function transformersModelOptions(records: DownloadedModelRecord[]): ModelOption[] {
  const seen = new Set<string>()
  const options: ModelOption[] = []
  for (const record of records) {
    if (seen.has(record.repo_id)) continue
    seen.add(record.repo_id)
    options.push({ modelId: record.repo_id, label: record.repo_id })
  }
  return options
}

export function modelOptionsFor(backend: BackendName, records: DownloadedModelRecord[]): ModelOption[] {
  if (backend === 'gguf') return ggufModelOptions(records.filter((r) => r.backend === 'gguf'))
  if (backend === 'transformers') return transformersModelOptions(records.filter((r) => r.backend === 'transformers'))
  return []
}

// Prefill from ?model=&quant=: prefer an exact match, then any option for the same
// repo, else the first available option.
export function pickPrefilledModelId(options: ModelOption[], paramModel: string | null, paramQuant: string | null): string {
  if (paramModel) {
    const withQuant = paramQuant ? `${paramModel}:${paramQuant}` : paramModel
    const exact = options.find((o) => o.modelId === withQuant)
    if (exact) return exact.modelId
    const sameRepo = options.find((o) => o.modelId === paramModel || o.modelId.startsWith(`${paramModel}:`))
    if (sameRepo) return sameRepo.modelId
  }
  return options[0]?.modelId ?? ''
}

// A short label for the transcript header, e.g. "Qwen3-14B" from "Qwen/Qwen3-14B:Q4_K_M.gguf".
export function shortModelName(modelId: string): string {
  const repoId = modelId.split(':')[0] ?? modelId
  const segments = repoId.split('/')
  return segments[segments.length - 1] || repoId
}

// e.g. "gguf Q4_K_M.gguf", "api", "transformers".
export function backendDisplayLabel(backend: BackendName, modelId: string): string {
  if (backend === 'gguf') {
    const quant = modelId.split(':')[1]
    return quant ? `gguf ${quant}` : 'gguf'
  }
  return backend
}
