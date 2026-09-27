// Queries and the run-starting mutation used by EvalsPage.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getEvalReport, listCases } from '../../api/endpoints'
import { queryKeys } from '../../api/hooks'
import type { EvalRunRequest } from '../../api/types'
import { startEvalRun, type ActiveEvalRun } from './activeRun'

export function useEvalReport() {
  return useQuery({ queryKey: queryKeys.evalReport, queryFn: getEvalReport })
}

// Every category in the dataset, for the run form's Category <select>. Reads the Dataset
// page's cases query, so saving or deleting a case there refreshes this too.
export function useDatasetCategories() {
  return useQuery({
    queryKey: queryKeys.datasetCases,
    queryFn: () => listCases(),
    select: (cases) => cases.map((testCase) => testCase.category),
  })
}

// Passive read of the in-progress run, if any: never fetches on its own (the value is
// only ever written by startEvalRun via setQueryData), so navigating back to this page
// just re-subscribes to whatever's already in the cache. gcTime is kept infinite so a
// run in progress survives the user browsing away for a while.
export function useActiveEvalRun() {
  return useQuery<ActiveEvalRun | null>({
    queryKey: queryKeys.activeEvalRun,
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
