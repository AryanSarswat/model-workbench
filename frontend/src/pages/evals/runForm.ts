// Pure helpers for the run form: turning form state into the request body, and
// deriving its option lists from data already fetched elsewhere on the page.
import type { BackendName, DownloadedModelRecord, EvalReportRow, EvalRunRequest } from '../../api/types'

export interface RunFormState {
  modelId: string
  backend: BackendName
  category: string // '' means "All categories"
  judgeModelId: string
}

export function buildRunRequest(form: RunFormState): EvalRunRequest {
  return {
    model_id: form.modelId.trim(),
    backend: form.backend,
    category: form.category === '' ? null : form.category,
    judge_model_id: form.judgeModelId.trim() === '' ? null : form.judgeModelId.trim(),
  }
}

// Sorted, de-duplicated category names for the Category <select>.
export function sortedCategories(categories: Iterable<string>): string[] {
  return [...new Set(categories)].sort()
}

// Model field suggestions for the chosen backend: gguf/transformers can only run
// against what's actually downloaded, so those suggestions come from listDownloaded();
// api has no local artifact, so its suggestions come from model ids the report already
// knows about. A gguf repo with several quants on disk needs "repo_id:quant" -- the
// format the backend's _resolve_gguf_path() accepts to pick one.
export function modelIdSuggestions(
  backend: BackendName,
  downloaded: DownloadedModelRecord[],
  reportRows: Pick<EvalReportRow, 'model_id' | 'backend'>[],
): string[] {
  if (backend === 'api') {
    return [...new Set(reportRows.filter((row) => row.backend === 'api').map((row) => row.model_id))].sort()
  }

  const matching = downloaded.filter((record) => record.backend === backend)
  if (backend === 'transformers') {
    return [...new Set(matching.map((record) => record.repo_id))].sort()
  }

  const quantsByRepo = new Map<string, Set<string>>()
  for (const record of matching) {
    const quants = quantsByRepo.get(record.repo_id) ?? new Set<string>()
    if (record.quant) quants.add(record.quant)
    quantsByRepo.set(record.repo_id, quants)
  }
  const suggestions: string[] = []
  for (const [repoId, quants] of quantsByRepo) {
    if (quants.size <= 1) suggestions.push(repoId)
    else for (const quant of quants) suggestions.push(`${repoId}:${quant}`)
  }
  return suggestions.sort()
}
