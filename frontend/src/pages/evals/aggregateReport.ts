// Turns the flat GET /evals/report rows into the comparison matrix the Evals screen
// renders: one row per (model_id, backend), one column per category. Pure and unit
// tested so the weighting/sorting rules don't have to be re-verified by hand in the UI.
import type { BackendName, EvalReportRow } from '../../api/types'

export interface MatrixCell {
  passed: number
  cases: number
  pct: number // 0..100, rounded
  tint: number // 0..0.5 alpha for the pass-rate background wash
}

export interface MatrixCategory {
  name: string
  cases: number // largest case count seen for this category across all rows
}

export interface MatrixRow {
  modelId: string
  backend: BackendName
  cells: (MatrixCell | null)[] // aligned with EvalMatrix.categories; null = not run
  overallPassed: number
  overallCases: number
  overallPct: number // 0..100, rounded
  tokensPerSec: number | null
  toolCallReliability: number | null // 0..1
  structuredOutputReliability: number | null // 0..1
  latestRunId: number
}

export interface EvalMatrix {
  categories: MatrixCategory[]
  rows: MatrixRow[]
}

export function aggregateReport(rows: EvalReportRow[]): EvalMatrix {
  const categoryNames = [...new Set(rows.map((row) => row.category))].sort()
  const categories: MatrixCategory[] = categoryNames.map((name) => ({
    name,
    cases: Math.max(...rows.filter((row) => row.category === name).map((row) => row.cases)),
  }))

  const groups = new Map<string, EvalReportRow[]>()
  for (const row of rows) {
    const key = `${row.model_id}\u0000${row.backend}`
    const group = groups.get(key)
    if (group) group.push(row)
    else groups.set(key, [row])
  }

  const matrixRows = [...groups.values()].map((groupRows): MatrixRow => {
    const byCategory = new Map(groupRows.map((row) => [row.category, row]))
    const cells = categoryNames.map((name): MatrixCell | null => {
      const row = byCategory.get(name)
      if (!row) return null
      const pct = Math.round((row.passed / row.cases) * 100)
      return { passed: row.passed, cases: row.cases, pct, tint: (Math.max(pct - 30, 0) / 70) * 0.5 }
    })
    const overallPassed = groupRows.reduce((sum, row) => sum + row.passed, 0)
    const overallCases = groupRows.reduce((sum, row) => sum + row.cases, 0)
    return {
      modelId: groupRows[0].model_id,
      backend: groupRows[0].backend,
      cells,
      overallPassed,
      overallCases,
      overallPct: overallCases > 0 ? Math.round((overallPassed / overallCases) * 100) : 0,
      tokensPerSec: weightedMean(groupRows, (row) => row.avg_tokens_per_sec),
      toolCallReliability: weightedMean(groupRows, (row) => row.tool_calling_reliability),
      structuredOutputReliability: weightedMean(groupRows, (row) => row.structured_output_reliability),
      latestRunId: Math.max(...groupRows.map((row) => row.latest_run_id)),
    }
  })

  matrixRows.sort((a, b) => b.overallPct - a.overallPct)
  return { categories, rows: matrixRows }
}

// Case-weighted mean of a nullable metric, skipping rows where it's null. Null when
// no row in the group has a value.
function weightedMean(rows: EvalReportRow[], pick: (row: EvalReportRow) => number | null): number | null {
  let weightedSum = 0
  let totalWeight = 0
  for (const row of rows) {
    const value = pick(row)
    if (value == null) continue
    weightedSum += value * row.cases
    totalWeight += row.cases
  }
  return totalWeight > 0 ? weightedSum / totalWeight : null
}
