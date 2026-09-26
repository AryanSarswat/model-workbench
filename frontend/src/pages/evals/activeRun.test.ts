import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EvalProgressEvent, EvalRun, EvalRunRequest } from '../../api/types'
import { activeRunKey, reportKey, startEvalRun, type ActiveEvalRun } from './activeRun'

const { runEval, listEvalRuns } = vi.hoisted(() => ({
  runEval: vi.fn(),
  listEvalRuns: vi.fn(),
}))

vi.mock('../../api/endpoints', () => ({ runEval, listEvalRuns }))

function makeRun(overrides: Partial<EvalRun> = {}): EvalRun {
  return {
    id: 1,
    model_id: 'org/model',
    backend: 'api',
    category: null,
    judge_model_id: null,
    status: 'running',
    total_cases: 0,
    completed_cases: 0,
    created_at: '2026-01-01T00:00:00Z',
    finished_at: null,
    ...overrides,
  }
}

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
  listEvalRuns.mockReset()
})

describe('startEvalRun', () => {
  it('finishes a zero-case run on its first (and only) event: status done, report invalidated', async () => {
    runEval.mockReturnValue(eventsOf([{ completed: 0, total: 0, current_case: null, done: true }]))
    listEvalRuns.mockResolvedValue([makeRun()])
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
        { completed: 0, total: 2, current_case: 'a', done: false },
        { completed: 1, total: 2, current_case: 'b', done: false },
        { completed: 2, total: 2, current_case: null, done: true },
      ]),
    )
    listEvalRuns.mockResolvedValue([makeRun()])
    const queryClient = new QueryClient()

    await startEvalRun(queryClient, request)
    expect(queryClient.getQueryData<ActiveEvalRun>(activeRunKey)?.status).toBe('streaming')

    await flushMicrotasks()

    const active = queryClient.getQueryData<ActiveEvalRun>(activeRunKey)
    expect(active?.status).toBe('done')
    expect(active?.event?.completed).toBe(2)
    expect(active?.runId).toBe(1)
  })

  it('marks the run as errored when the stream ends without a terminal event', async () => {
    runEval.mockReturnValue(eventsOf([{ completed: 0, total: 2, current_case: 'a', done: false }]))
    listEvalRuns.mockResolvedValue([makeRun()])
    const queryClient = new QueryClient()

    await startEvalRun(queryClient, request)
    await flushMicrotasks()

    const active = queryClient.getQueryData<ActiveEvalRun>(activeRunKey)
    expect(active?.status).toBe('error')
    expect(active?.error).toBe('stream ended before the run finished')
  })

  it('keeps consuming when the run-id lookup fails, instead of abandoning the run', async () => {
    runEval.mockReturnValue(
      eventsOf([
        { completed: 0, total: 1, current_case: 'a', done: false },
        { completed: 1, total: 1, current_case: null, done: true },
      ]),
    )
    listEvalRuns.mockRejectedValue(new Error('network error'))
    const queryClient = new QueryClient()

    await startEvalRun(queryClient, request)
    await flushMicrotasks()

    const active = queryClient.getQueryData<ActiveEvalRun>(activeRunKey)
    expect(active?.status).toBe('done')
    expect(active?.runId).toBeNull()
  })
})
