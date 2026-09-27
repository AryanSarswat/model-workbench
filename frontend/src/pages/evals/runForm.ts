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
// knows about.
export function modelIdSuggestions(
  backend: BackendName,
  downloaded: DownloadedModelRecord[],
  reportRows: Pick<EvalReportRow, 'model_id' | 'backend'>[],
): string[] {
  if (backend === 'api') {
    return [...new Set(reportRows.filter((row) => row.backend === 'api').map((row) => row.model_id))].sort()
  }

  const matching = downloaded.filter((record) => record.backend === backend)
  return [...new Set(matching.map((record) => record.model_id))].sort()
}
