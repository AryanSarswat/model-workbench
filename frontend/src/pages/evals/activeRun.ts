// Drives a running eval and keeps its progress in the TanStack Query cache instead of
// component state. The backend ties a run's lifetime to the POST /evals/run request
// (a client disconnect marks the run failed -- see docs/architecture.md's Eval engine
// section), so this must NOT be cancelled when EvalsPage unmounts: it's a plain async
// function, not tied to an effect or an AbortSignal, so navigating away and back just
// re-subscribes to the same cache entry via useActiveEvalRun().
import type { QueryClient } from '@tanstack/react-query'
import { listEvalRuns, runEval } from '../../api/endpoints'
import type { EvalProgressEvent, EvalRunRequest } from '../../api/types'

export const activeRunKey = ['evals', 'active-run'] as const
// Must match the query key EvalsPage's useEvalReport/useEvalRuns use, so a run's
// completion invalidates the data the matrix and future runs read.
export const reportKey = ['evals', 'report'] as const
export const runsKey = ['evals', 'runs'] as const

export type ActiveRunStatus = 'streaming' | 'done' | 'error'

export interface ActiveEvalRun {
  request: EvalRunRequest
  runId: number | null
  event: EvalProgressEvent | null
  status: ActiveRunStatus
  error: string | null
}

// The SSE events carry no run id, so once the stream has started we look it up: the
// newest run matching this request's model+backend that's still running.
async function resolveRunId(request: EvalRunRequest): Promise<number | null> {
  const runs = await listEvalRuns()
  const backend = request.backend ?? 'api'
  const match = runs.find((run) => run.status === 'running' && run.model_id === request.model_id && run.backend === backend)
  return match?.id ?? null
}

// Starts the run. Resolves once the first progress event has arrived (or rejects with
// the pre-stream error, e.g. missing_hf_api_key) so the caller can show that in the
// run form; the rest of the stream is then consumed in the background.
export async function startEvalRun(queryClient: QueryClient, request: EvalRunRequest): Promise<void> {
  const iterator = runEval(request)
  const first = await iterator.next()
  if (first.done) return
  const runId = await resolveRunId(request)
  queryClient.setQueryData<ActiveEvalRun>(activeRunKey, {
    request,
    runId,
    event: first.value,
    status: 'streaming',
    error: null,
  })
  void consume(iterator, queryClient, request, runId)
}

async function consume(
  iterator: AsyncGenerator<EvalProgressEvent>,
  queryClient: QueryClient,
  request: EvalRunRequest,
  knownRunId: number | null,
): Promise<void> {
  let runId = knownRunId
  try {
    for (;;) {
      const { value, done } = await iterator.next()
      if (done) return
      if (runId == null) runId = await resolveRunId(request)
      queryClient.setQueryData<ActiveEvalRun>(activeRunKey, {
        request,
        runId,
        event: value,
        status: value.error ? 'error' : value.done ? 'done' : 'streaming',
        error: value.error ?? null,
      })
      if (value.done) {
        await queryClient.invalidateQueries({ queryKey: reportKey })
        await queryClient.invalidateQueries({ queryKey: runsKey })
        return
      }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    queryClient.setQueryData<ActiveEvalRun | undefined>(activeRunKey, (prev) =>
      prev ? { ...prev, status: 'error', error: message } : prev,
    )
  }
}
