// Pure helpers for the Model detail page: matching options to what's on disk or
// downloading, and building the various playground/eval links.
import type { BackendName, DownloadJob, DownloadedModelRecord, EvalReportRow, FeasibilityOption, ModelDetail } from '../../api/types'
import { formatGb, formatParamCount } from '../../lib/format'
import { playgroundPath } from '../../lib/links'

export function splitModelId(id: string): { author: string; name: string } {
  const slash = id.indexOf('/')
  return slash === -1 ? { author: '', name: id } : { author: id.slice(0, slash), name: id.slice(slash + 1) }
}

// The file-size or param-count subtitle shown next to an option's backend reason.
export function optionSizeLabel(option: FeasibilityOption, detail: ModelDetail): string | null {
  if (option.backend === 'gguf') {
    const file = detail.gguf_files.find((f) => f.filename === option.filename)
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
  if (gguf?.quant) return playgroundPath({ model: modelId, backend: 'gguf', quant: gguf.quant })
  if (downloaded.some((r) => r.repo_id === modelId && r.backend === 'transformers')) {
    return playgroundPath({ model: modelId, backend: 'transformers' })
  }
  return playgroundPath({ model: modelId, backend: 'api' })
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
