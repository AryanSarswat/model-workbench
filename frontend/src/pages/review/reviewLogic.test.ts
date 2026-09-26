import { describe, expect, it } from 'vitest'
import type { EvalResult } from '../../api/types'
import { countByStatus, filterResults, nextUnreviewedCaseId, verdictUpdatePayload } from './reviewLogic'

function result(overrides: Partial<EvalResult> & Pick<EvalResult, 'id' | 'case_id'>): EvalResult {
  return {
    run_id: 1,
    category: 'coding',
    response: '{}',
    error: null,
    structured_output_mode: null,
    native_tool_calling: false,
    retries: 0,
    tools_called: '',
    assertions_passed: 1,
    assertions_total: 1,
    assertions_detail: '[]',
    judge_score: null,
    judge_rationale: null,
    manual_verdict: null,
    manual_notes: null,
    response_metric_id: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('filterResults / countByStatus', () => {
  const results = [
    result({ id: 1, case_id: 'a', assertions_passed: 1, assertions_total: 1 }), // auto-pass, unreviewed
    result({ id: 2, case_id: 'b', assertions_passed: 0, assertions_total: 1 }), // auto-fail, unreviewed
    result({ id: 3, case_id: 'c', assertions_passed: 0, assertions_total: 1, manual_verdict: 'pass' }), // manual override to pass
    result({ id: 4, case_id: 'd', assertions_passed: 1, assertions_total: 1, manual_verdict: 'fail' }), // manual override to fail
  ]

  it('counts pass/fail via resultPassed (manual verdict wins) and unreviewed via manual_verdict', () => {
    expect(countByStatus(results)).toEqual({ total: 4, passed: 2, failed: 2, unreviewed: 2 })
  })

  it('"failed" filters by the same resultPassed rule, not raw assertion counts', () => {
    expect(filterResults(results, 'failed').map((r) => r.case_id)).toEqual(['b', 'd'])
  })

  it('"unreviewed" filters by manual_verdict alone, regardless of pass/fail', () => {
    expect(filterResults(results, 'unreviewed').map((r) => r.case_id)).toEqual(['a', 'b'])
  })

  it('"all" returns everything', () => {
    expect(filterResults(results, 'all')).toHaveLength(4)
  })
})

describe('nextUnreviewedCaseId', () => {
  const results = [
    result({ id: 1, case_id: 'a', manual_verdict: 'pass' }),
    result({ id: 2, case_id: 'b' }),
    result({ id: 3, case_id: 'c' }),
    result({ id: 4, case_id: 'd', manual_verdict: 'fail' }),
  ]

  it('finds the next unreviewed case after the current one', () => {
    expect(nextUnreviewedCaseId(results, 'b')).toBe('c')
  })

  it('wraps around to the start of the list', () => {
    expect(nextUnreviewedCaseId(results, 'c')).toBe('b')
  })

  it('starts from the first unreviewed case when nothing is selected yet', () => {
    expect(nextUnreviewedCaseId(results, null)).toBe('b')
  })

  it('returns null when every case has been reviewed', () => {
    const allReviewed = results.map((r) => ({ ...r, manual_verdict: 'pass' as const }))
    expect(nextUnreviewedCaseId(allReviewed, 'a')).toBeNull()
  })
})

describe('verdictUpdatePayload', () => {
  it('sends the chosen verdict and trimmed notes', () => {
    expect(verdictUpdatePayload('fail', '  too slow  ')).toEqual({ manual_verdict: 'fail', manual_notes: 'too slow' })
  })

  it('"clear" sends a null verdict', () => {
    expect(verdictUpdatePayload('clear', 'some notes')).toEqual({ manual_verdict: null, manual_notes: 'some notes' })
  })

  it('sends null notes for blank input', () => {
    expect(verdictUpdatePayload('pass', '   ')).toEqual({ manual_verdict: 'pass', manual_notes: null })
  })
})
