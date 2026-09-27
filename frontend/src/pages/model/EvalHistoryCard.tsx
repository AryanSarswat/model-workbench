import { type UseQueryResult } from '@tanstack/react-query'
import { Link } from 'react-router'
import type { EvalReportRow } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { BACKENDS } from '../../lib/backends'
import styles from './ModelPage.module.css'
import { bestEvalBackend } from './modelHelpers'

export function EvalHistoryCard({ modelId, evalReportQuery }: { modelId: string; evalReportQuery: UseQueryResult<EvalReportRow[]> }) {
  if (evalReportQuery.isPending) {
    return (
      <section aria-labelledby="hist" className={styles.historySection}>
        <h2 id="hist" className={styles.historyTitle}>On your test cases</h2>
        <p>Loading…</p>
      </section>
    )
  }
  if (evalReportQuery.isError) {
    return (
      <section aria-labelledby="hist" className={styles.historySection}>
        <h2 id="hist" className={styles.historyTitle}>On your test cases</h2>
        <ErrorNotice error={evalReportQuery.error} />
      </section>
    )
  }

  const rows = evalReportQuery.data.filter((row) => row.model_id === modelId)
  if (rows.length === 0) {
    return (
      <section aria-labelledby="hist" className={styles.historySection}>
        <h2 id="hist" className={styles.historyTitle}>On your test cases</h2>
        <p className={styles.historyEmpty}>
          Not evaluated yet. <Link to={`/evals?model=${encodeURIComponent(modelId)}`}>Run eval</Link>
        </p>
      </section>
    )
  }

  const backend = bestEvalBackend(rows)
  const backendRows = rows.filter((row) => row.backend === backend)
  const totalCases = backendRows.reduce((sum, row) => sum + row.cases, 0)
  const totalPassed = backendRows.reduce((sum, row) => sum + row.passed, 0)

  return (
    <section aria-labelledby="hist" className={styles.historySection}>
      <div className={styles.historyHeader}>
        <h2 id="hist" className={styles.historyTitle}>On your test cases</h2>
        {backend && <span className={styles.historyBackend}>{BACKENDS[backend].label}</span>}
      </div>
      <div>
        {backendRows.map((row) => (
          <div key={row.category} className={styles.historyRow}>
            <span>{row.category}</span>
            <div className={styles.historyBarTrack}>
              <div className={styles.historyBarFill} style={{ width: `${row.pass_rate * 100}%` }} />
            </div>
            <span className={styles.historyPct}>{Math.round(row.pass_rate * 100)}%</span>
          </div>
        ))}
      </div>
      <div className={styles.historyFooter}>
        <span>
          {totalPassed} of {totalCases} cases passed
        </span>
        <Link to="/evals">Compare</Link>
      </div>
    </section>
  )
}
