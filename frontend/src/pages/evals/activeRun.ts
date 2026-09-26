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
// Must match the query key EvalsPage's useEvalReport uses, so a run's completion
// invalidates the data the matrix reads.
export const reportKey = ['evals', 'report'] as const

export type ActiveRunStatus = 'streaming' | 'done' | 'error'

export interface ActiveEvalRun {
  request: EvalRunRequest
  runId: number | null
  event: EvalProgressEvent | null
  status: ActiveRunStatus
  error: string | null
}

// The SSE events carry no run id, so once the stream has started we look it up: the
// newest run matching this request's model+backend that's still running. A lookup
// failure resolves to null rather than throwing -- the caller keeps consuming the
// stream regardless and retries the lookup on the next event.
async function resolveRunId(request: EvalRunRequest): Promise<number | null> {
  const runs = await listEvalRuns()
  const backend = request.backend ?? 'api'
  const match = runs.find((run) => run.status === 'running' && run.model_id === request.model_id && run.backend === backend)
  return match?.id ?? null
}

// Applies one progress event to the cache: resolves the run id if it isn't known yet,
// records the event/status, and invalidates the report once the run is done. Shared by
// the first event (handled inline in startEvalRun) and every later one (in consume()),
// so a run that finishes on its very first event -- e.g. an empty category, zero cases
// -- is handled identically to one that streams for a while first.
async function applyEvent(
  queryClient: QueryClient,
  request: EvalRunRequest,
  knownRunId: number | null,
  event: EvalProgressEvent,
): Promise<{ runId: number | null; done: boolean }> {
  const runId = knownRunId ?? (await resolveRunId(request).catch(() => null))
  queryClient.setQueryData<ActiveEvalRun>(activeRunKey, {
    request,
    runId,
    event,
    status: event.error ? 'error' : event.done ? 'done' : 'streaming',
    error: event.error ?? null,
  })
  if (event.done) {
    await queryClient.invalidateQueries({ queryKey: reportKey })
  }
  return { runId, done: event.done }
}

// Starts the run. Resolves once the first progress event has arrived (or rejects with
// the pre-stream error, e.g. missing_hf_api_key) so the caller can show that in the
// run form; the rest of the stream, if any, is then consumed in the background.
export async function startEvalRun(queryClient: QueryClient, request: EvalRunRequest): Promise<void> {
  const iterator = runEval(request)
  const first = await iterator.next()
  if (first.done) {
    // Defensive: the backend always yields a terminal event, even for zero cases, so
    // this means the connection dropped before any bytes arrived.
    queryClient.setQueryData<ActiveEvalRun>(activeRunKey, {
      request,
      runId: null,
      event: null,
      status: 'error',
      error: 'stream ended before the run finished',
    })
    return
  }
  const { runId, done } = await applyEvent(queryClient, request, null, first.value)
  if (done) return
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
      if (done) {
        // The stream closed without ever sending a done:true event -- a dropped
        // connection. Merge into whatever's already cached rather than clobbering it.
        queryClient.setQueryData<ActiveEvalRun | undefined>(activeRunKey, (prev) =>
          prev ? { ...prev, status: 'error', error: 'stream ended before the run finished' } : prev,
        )
        return
      }
      const result = await applyEvent(queryClient, request, runId, value)
      runId = result.runId
      if (result.done) return
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    queryClient.setQueryData<ActiveEvalRun | undefined>(activeRunKey, (prev) =>
      prev ? { ...prev, status: 'error', error: message } : prev,
    )
  }
}
