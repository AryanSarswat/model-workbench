import { describe, expect, it } from 'vitest'
import type { EvalReportRow } from '../../api/types'
import { aggregateReport } from './aggregateReport'

function row(overrides: Partial<EvalReportRow> & Pick<EvalReportRow, 'model_id' | 'backend' | 'category'>): EvalReportRow {
  return {
    cases: 10,
    passed: 5,
    pass_rate: 0.5,
    avg_tokens_per_sec: null,
    avg_ttft_ms: null,
    structured_output_reliability: null,
    tool_calling_reliability: null,
    latest_run_id: 1,
    ...overrides,
  }
}

describe('aggregateReport', () => {
  it('case-weights tok/s and reliability means across a model+backend group, skipping nulls', () => {
    const rows = [
      row({ model_id: 'm', backend: 'api', category: 'coding', cases: 30, passed: 30, avg_tokens_per_sec: 60, tool_calling_reliability: 0.9 }),
      row({ model_id: 'm', backend: 'api', category: 'general', cases: 10, passed: 10, avg_tokens_per_sec: 20, tool_calling_reliability: null }),
    ]
    const { rows: matrix } = aggregateReport(rows)
    expect(matrix).toHaveLength(1)
    // (60*30 + 20*10) / 40 = 50
    expect(matrix[0].tokensPerSec).toBe(50)
    // only the coding row has a value, so the mean is just that value
    expect(matrix[0].toolCallReliability).toBe(0.9)
  })

  it('marks a category the group never ran as a missing cell, and excludes it from Overall', () => {
    const rows = [
      row({ model_id: 'm', backend: 'gguf', category: 'coding', cases: 20, passed: 15 }),
      // a different model ran 'general' so it appears as a column, but 'm' didn't
      row({ model_id: 'other', backend: 'api', category: 'general', cases: 5, passed: 5 }),
    ]
    const { categories, rows: matrix } = aggregateReport(rows)
    expect(categories.map((c) => c.name)).toEqual(['coding', 'general'])

    const mRow = matrix.find((r) => r.modelId === 'm')!
    expect(mRow.cells).toEqual([
      { passed: 15, cases: 20, pct: 75, tint: (Math.max(75 - 30, 0) / 70) * 0.5 },
      null,
    ])
    // Overall only counts categories the group actually ran.
    expect(mRow.overallPassed).toBe(15)
    expect(mRow.overallCases).toBe(20)
    expect(mRow.overallPct).toBe(75)
  })

  it('sorts groups by Overall pass rate descending', () => {
    const rows = [
      row({ model_id: 'low', backend: 'api', category: 'coding', cases: 10, passed: 3 }),
      row({ model_id: 'high', backend: 'api', category: 'coding', cases: 10, passed: 9 }),
      row({ model_id: 'mid', backend: 'api', category: 'coding', cases: 10, passed: 6 }),
    ]
    const { rows: matrix } = aggregateReport(rows)
    expect(matrix.map((r) => r.modelId)).toEqual(['high', 'mid', 'low'])
  })

  it('takes the max latest_run_id across a group’s categories', () => {
    const rows = [
      row({ model_id: 'm', backend: 'api', category: 'coding', latest_run_id: 5 }),
      row({ model_id: 'm', backend: 'api', category: 'general', latest_run_id: 9 }),
    ]
    const { rows: matrix } = aggregateReport(rows)
    expect(matrix[0].latestRunId).toBe(9)
  })
})
