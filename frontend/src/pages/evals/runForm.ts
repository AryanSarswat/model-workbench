// Pure helpers for the run form: turning form state into the request body, and
// deriving its option lists from data already fetched elsewhere on the page.
import type { BackendName, EvalRunRequest } from '../../api/types'

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

// Sorted, de-duplicated model ids for the Model field's datalist: downloaded repos
// plus anything that's already shown up in the comparison report.
export function modelIdSuggestions(downloadedRepoIds: Iterable<string>, reportModelIds: Iterable<string>): string[] {
  return [...new Set([...downloadedRepoIds, ...reportModelIds])].sort()
}
