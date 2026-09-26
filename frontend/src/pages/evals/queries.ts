// Queries and the run-starting mutation used by EvalsPage.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getEvalReport, listCases, listDownloaded } from '../../api/endpoints'
import type { EvalRunRequest } from '../../api/types'
import { activeRunKey, reportKey, startEvalRun, type ActiveEvalRun } from './activeRun'

export function useEvalReport() {
  return useQuery({ queryKey: reportKey, queryFn: getEvalReport })
}

// Every category in the dataset, for the run form's Category <select>.
export function useDatasetCategories() {
  return useQuery({
    queryKey: ['evals', 'dataset-categories'] as const,
    queryFn: async () => (await listCases()).map((testCase) => testCase.category),
  })
}

export function useDownloadedModels() {
  return useQuery({
    queryKey: ['evals', 'downloaded-models'] as const,
    queryFn: listDownloaded,
  })
}

// Passive read of the in-progress run, if any: never fetches on its own (the value is
// only ever written by startEvalRun via setQueryData), so navigating back to this page
// just re-subscribes to whatever's already in the cache. gcTime is kept infinite so a
// run in progress survives the user browsing away for a while.
export function useActiveEvalRun() {
  return useQuery<ActiveEvalRun | null>({
    queryKey: activeRunKey,
    queryFn: () => null,
    staleTime: Infinity,
    gcTime: Infinity,
  })
}

export function useStartEvalRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: EvalRunRequest) => startEvalRun(queryClient, request),
  })
}
