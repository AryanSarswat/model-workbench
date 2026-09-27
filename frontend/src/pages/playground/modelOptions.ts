import type { BackendName, DownloadedModelRecord } from '../../api/types'

export interface ModelOption {
  modelId: string // value to send as ChatRequest.model_id
  label: string
  unloadable: { quant: string; reason: string } | null // a GGUF the local llama.cpp can't read
}

// "PQ2_0" from "Ternary-Bonsai-2-27B-PQ2_0.gguf" or "model.Q4_K_M.gguf".
function quantName(filename: string): string {
  return filename.replace(/\.gguf$/i, '').split(/[-.]/).pop() || filename
}

// The backend returns a "repo_id:quant" model_id only when several quants of that repo
// are downloaded -- then the label names the quant too.
export function ggufModelOptions(records: DownloadedModelRecord[]): ModelOption[] {
  return records.map((record) => {
    const label = record.model_id.includes(':') ? `${record.repo_id} (${record.quant})` : record.repo_id
    const unloadable = record.unsupported_reason
      ? { quant: quantName(record.quant ?? ''), reason: record.unsupported_reason }
      : null
    return { modelId: record.model_id, label, unloadable }
  })
}

// Repeated downloads of one transformers repo share a model_id (the registry resolves it
// to the most recently downloaded row) -- dedupe them.
export function transformersModelOptions(records: DownloadedModelRecord[]): ModelOption[] {
  const seen = new Set<string>()
  const options: ModelOption[] = []
  for (const record of records) {
    if (seen.has(record.model_id)) continue
    seen.add(record.model_id)
    options.push({ modelId: record.model_id, label: record.model_id, unloadable: null })
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
