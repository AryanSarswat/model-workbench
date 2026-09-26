// Queries and mutations used by ReviewPage.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getCase, getEvalRunResults, listEvalRuns, updateEvalResult } from '../../api/endpoints'
import type { ManualVerdictUpdate } from '../../api/types'

const reviewKeys = {
  run: (runId: number) => ['eval-review', 'run', runId] as const,
  results: (runId: number) => ['eval-review', 'results', runId] as const,
  case: (caseId: string) => ['eval-review', 'case', caseId] as const,
}

// No GET /evals/runs/{id} endpoint exists -- list and find, like the Evals screen does
// to resolve a running eval's id.
export function useEvalRun(runId: number) {
  return useQuery({
    queryKey: reviewKeys.run(runId),
    queryFn: async () => (await listEvalRuns()).find((run) => run.id === runId) ?? null,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  })
}

export function useEvalRunResults(runId: number, isRunning: boolean) {
  return useQuery({
    queryKey: reviewKeys.results(runId),
    queryFn: () => getEvalRunResults(runId),
    refetchInterval: isRunning ? 2000 : false,
  })
}

// The Prompt panel's actual fetch for the selected case. 404 means the case was since
// deleted from the dataset -- the page shows a fallback message for that, not an error.
export function useCase(caseId: string) {
  return useQuery({ queryKey: reviewKeys.case(caseId), queryFn: () => getCase(caseId), retry: false })
}

// A passive read of whatever useCase() has already cached for this case, used by the
// case list to show a one-line prompt snippet only when it's already been fetched --
// never triggers its own request.
export function useCachedCase(caseId: string) {
  return useQuery({ queryKey: reviewKeys.case(caseId), queryFn: () => getCase(caseId), enabled: false, staleTime: Infinity })
}

export function useUpdateEvalResult(runId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ resultId, update }: { resultId: number; update: ManualVerdictUpdate }) => updateEvalResult(resultId, update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reviewKeys.results(runId) })
      // Must match EvalsPage's report query key so the matrix picks up the new verdict.
      queryClient.invalidateQueries({ queryKey: ['evals', 'report'] })
    },
  })
}
