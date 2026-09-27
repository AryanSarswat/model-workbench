// Queries and mutations used by ReviewPage.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { getCase, getEvalRun, getEvalRunResults, updateEvalResult } from '../../api/endpoints'
import type { ManualVerdictUpdate } from '../../api/types'
import { queryKeys } from '../../api/hooks'

export function useEvalRun(runId: number) {
  return useQuery({
    queryKey: queryKeys.evalRun(runId),
    queryFn: () => getEvalRun(runId),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  })
}

export function useEvalRunResults(runId: number, isRunning: boolean) {
  const queryClient = useQueryClient()
  // The 2s polls of this query and of the run's own status aren't synchronized, so the
  // run can flip out of "running" right after a results poll and before the next one --
  // missing whichever case completed last. Refetch once more the moment that happens.
  const wasRunning = useRef(isRunning)
  useEffect(() => {
    if (wasRunning.current && !isRunning) {
      queryClient.invalidateQueries({ queryKey: queryKeys.evalRunResults(runId) })
    }
    wasRunning.current = isRunning
  }, [isRunning, runId, queryClient])

  return useQuery({
    queryKey: queryKeys.evalRunResults(runId),
    queryFn: () => getEvalRunResults(runId),
    refetchInterval: isRunning ? 2000 : false,
  })
}

// The Prompt panel's fetch for the selected case. 404 means the case was since deleted
// from the dataset -- the page shows a fallback message for that, not an error.
export function useCase(caseId: string) {
  return useQuery({ queryKey: queryKeys.testCase(caseId), queryFn: () => getCase(caseId), retry: false })
}

export function useUpdateEvalResult(runId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ resultId, update }: { resultId: number; update: ManualVerdictUpdate }) => updateEvalResult(resultId, update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.evalRunResults(runId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.evalReport })
    },
  })
}
