import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EvalProgressEvent, EvalRunRequest } from '../../api/types'
import { activeRunKey, reportKey, startEvalRun, type ActiveEvalRun } from './activeRun'

const { runEval } = vi.hoisted(() => ({ runEval: vi.fn() }))

vi.mock('../../api/endpoints', () => ({ runEval }))

// The shape postSse() yields: a plain async generator over the request's events.
async function* eventsOf(events: EvalProgressEvent[]): AsyncGenerator<EvalProgressEvent> {
  for (const event of events) yield event
}

const request: EvalRunRequest = { model_id: 'org/model', backend: 'api', category: null, judge_model_id: null }

// Lets the background consume() loop (started but not awaited by startEvalRun) drain.
function flushMicrotasks() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

beforeEach(() => {
  runEval.mockReset()
})

describe('startEvalRun', () => {
  it('finishes a zero-case run on its first (and only) event: status done, report invalidated', async () => {
    runEval.mockReturnValue(eventsOf([{ run_id: 7, completed: 0, total: 0, current_case: null, done: true }]))
    const queryClient = new QueryClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    await startEvalRun(queryClient, request)

    const active = queryClient.getQueryData<ActiveEvalRun>(activeRunKey)
    expect(active?.status).toBe('done')
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: reportKey })
  })

  it('streams progress and finishes normally once every case completes', async () => {
    runEval.mockReturnValue(
      eventsOf([
        { run_id: 7, completed: 0, total: 2, current_case: 'a', done: false },
        { run_id: 7, completed: 1, total: 2, current_case: 'b', done: false },
        { run_id: 7, completed: 2, total: 2, current_case: null, done: true },
      ]),
    )
    const queryClient = new QueryClient()

    await startEvalRun(queryClient, request)
    expect(queryClient.getQueryData<ActiveEvalRun>(activeRunKey)?.status).toBe('streaming')

    await flushMicrotasks()

    const active = queryClient.getQueryData<ActiveEvalRun>(activeRunKey)
    expect(active?.status).toBe('done')
    expect(active?.event?.completed).toBe(2)
    expect(active?.runId).toBe(7)
  })

  it('marks the run as errored when the stream ends without a terminal event', async () => {
    runEval.mockReturnValue(eventsOf([{ run_id: 7, completed: 0, total: 2, current_case: 'a', done: false }]))
    const queryClient = new QueryClient()

    await startEvalRun(queryClient, request)
    await flushMicrotasks()

    const active = queryClient.getQueryData<ActiveEvalRun>(activeRunKey)
    expect(active?.status).toBe('error')
    expect(active?.error).toBe('stream ended before the run finished')
  })
})
