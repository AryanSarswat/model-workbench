// Pure helpers for the Model detail page: matching options to what's on disk or
// downloading, and building the various playground/eval links.
import type { BackendName, DownloadJob, DownloadedModelRecord, EvalReportRow, FeasibilityOption, ModelDetail } from '../../api/types'
import { formatGb } from '../../lib/format'

export function splitModelId(id: string): { author: string; name: string } {
  const slash = id.indexOf('/')
  return slash === -1 ? { author: '', name: id } : { author: id.slice(0, slash), name: id.slice(slash + 1) }
}

// A feasibility option's label is a GGUF filename, or "transformers (DTYPE)".
export function optionBackend(label: string): 'gguf' | 'transformers' {
  return label.toLowerCase().endsWith('.gguf') ? 'gguf' : 'transformers'
}

export function formatParamCount(count: number): string {
  return `${(count / 1e9).toFixed(1)}B params`
}

// The file-size or param-count subtitle shown next to an option's backend reason.
export function optionSizeLabel(option: FeasibilityOption, detail: ModelDetail): string | null {
  if (optionBackend(option.label) === 'gguf') {
    const file = detail.gguf_files.find((f) => f.filename === option.label)
    return file ? `${formatGb(file.size_bytes)} file` : null
  }
  return detail.parameter_count == null ? null : formatParamCount(detail.parameter_count)
}

export function findDownloadedGguf(
  records: DownloadedModelRecord[],
  modelId: string,
  filename: string,
): DownloadedModelRecord | undefined {
  return records.find((r) => r.repo_id === modelId && r.backend === 'gguf' && r.quant === filename)
}

export function findDownloadedSnapshot(records: DownloadedModelRecord[], modelId: string): DownloadedModelRecord | undefined {
  return records.find((r) => r.repo_id === modelId && r.backend === 'transformers')
}

export function findActiveGgufJob(jobs: DownloadJob[], modelId: string, filename: string): DownloadJob | undefined {
  return jobs.find((j) => j.repo_id === modelId && j.kind === 'gguf' && j.filename === filename)
}

export function findActiveSnapshotJob(jobs: DownloadJob[], modelId: string): DownloadJob | undefined {
  return jobs.find((j) => j.repo_id === modelId && j.kind === 'snapshot')
}

// The header's "Open in Playground" target: prefer a GGUF already on disk, then a
// transformers snapshot, else fall back to the (always-available) API backend.
export function playgroundLink(modelId: string, downloaded: DownloadedModelRecord[]): string {
  const gguf = downloaded.find((r) => r.repo_id === modelId && r.backend === 'gguf' && r.quant)
  if (gguf?.quant) return optionPlaygroundLink(modelId, 'gguf', gguf.quant)
  if (downloaded.some((r) => r.repo_id === modelId && r.backend === 'transformers')) {
    return optionPlaygroundLink(modelId, 'transformers')
  }
  return optionPlaygroundLink(modelId, 'api')
}

export function optionPlaygroundLink(modelId: string, backend: BackendName, filename?: string): string {
  const params = new URLSearchParams({ model: modelId, backend })
  if (backend === 'gguf' && filename) params.set('quant', filename)
  return `/playground?${params}`
}

// The backend with the most evaluated cases for this model, used to pick which set of
// per-category rows to show in "On your test cases".
export function bestEvalBackend(rows: EvalReportRow[]): BackendName | null {
  const totals = new Map<BackendName, number>()
  for (const row of rows) totals.set(row.backend, (totals.get(row.backend) ?? 0) + row.cases)
  let best: BackendName | null = null
  let bestCases = -1
  for (const [backend, cases] of totals) {
    if (cases > bestCases) {
      best = backend
      bestCases = cases
    }
  }
  return best
}
