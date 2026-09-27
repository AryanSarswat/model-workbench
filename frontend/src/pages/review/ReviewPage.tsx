import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import type { EvalResult } from '../../api/types'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { SegmentedControl } from '../../components/SegmentedControl'
import { BACKENDS } from '../../lib/backends'
import { formatRelative } from '../../lib/format'
import styles from './ReviewPage.module.css'
import { AssertionsSection, CasePanel, JudgeSection, VerdictForm } from './CasePanel'
import { useEvalRun, useEvalRunResults } from './queries'
import { countByStatus, filterResults, nextUnreviewedCaseId, type CaseFilter } from './reviewLogic'

export default function ReviewPage() {
  const { runId: runIdParam } = useParams()
  const runId = Number(runIdParam)
  const [searchParams, setSearchParams] = useSearchParams()
  const [filter, setFilter] = useState<CaseFilter>('all')

  const runQuery = useEvalRun(runId)
  const isRunning = runQuery.data?.status === 'running'
  const resultsQuery = useEvalRunResults(runId, isRunning)

  const results = resultsQuery.data ?? []
  const run = runQuery.data ?? null
  const counts = countByStatus(results)
  const filtered = filterResults(results, filter)

  // A selection the current filter hides (or that no longer exists) is treated as
  // cleared: fall back to the first row that's actually visible in the list, so the
  // detail panel always matches what's highlighted (or "No cases match this filter"
  // when the filtered list is empty).
  const requestedCaseId = searchParams.get('case')
  const selectedCaseId = filtered.some((result) => result.case_id === requestedCaseId) ? requestedCaseId : (filtered[0]?.case_id ?? null)
  const selectedResult = filtered.find((result) => result.case_id === selectedCaseId) ?? null

  function selectCase(caseId: string) {
    const next = new URLSearchParams(searchParams)
    next.set('case', caseId)
    setSearchParams(next)
  }

  function goToNextUnreviewed() {
    const nextId = nextUnreviewedCaseId(filtered, selectedCaseId)
    if (nextId) selectCase(nextId)
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div className={styles.heading}>
          <nav aria-label="Breadcrumb" className={`eyebrow ${styles.breadcrumb}`}>
            <Link to="/evals">Evals</Link>
            <span>/</span>
            <span>Run {runId}</span>
          </nav>
          <h1 className={styles.title}>
            {run?.model_id ?? `Run ${runId}`} on <em>{run?.category ?? 'all categories'}</em>
          </h1>
          <div className={styles.meta}>
            {run &&
              [
                BACKENDS[run.backend].label,
                run.judge_model_id ? `judged by ${run.judge_model_id}` : 'no judge',
                `${run.total_cases} cases`,
                run.status === 'running' ? 'running' : `${run.status} ${formatRelative(run.finished_at)}`,
              ].join(' · ')}
          </div>
        </div>
        <div className={styles.summary}>
          <Chip tone="fit" className={styles.summaryChip}>
            {counts.passed} passed
          </Chip>
          <Chip tone="nofit" className={styles.summaryChip}>
            {counts.failed} failed
          </Chip>
          <Chip tone="tight" className={styles.summaryChip}>
            {counts.unreviewed} unreviewed
          </Chip>
        </div>
      </header>

      <div className={styles.body}>
        {resultsQuery.isPending ? (
          <p className="eyebrow">Loading…</p>
        ) : resultsQuery.isError ? (
          <ErrorNotice error={resultsQuery.error} />
        ) : (
          <>
            <nav aria-label="Cases" className={styles.caseNav}>
              <div className={styles.filterRow}>
                <SegmentedControl
                  label="Show"
                  value={filter}
                  onChange={setFilter}
                  options={[
                    { value: 'all' as const, label: `All ${counts.total}` },
                    { value: 'failed' as const, label: `Failed ${counts.failed}` },
                    { value: 'unreviewed' as const, label: `Unreviewed ${counts.unreviewed}` },
                  ]}
                />
              </div>
              <div className={styles.caseList}>
                {filtered.map((result) => (
                  <CaseRow
                    key={result.id}
                    result={result}
                    selected={result.case_id === selectedCaseId}
                    onSelect={() => selectCase(result.case_id)}
                  />
                ))}
              </div>
            </nav>

            {selectedResult ? (
              <>
                <CasePanel result={selectedResult} />
                <aside className={styles.aside}>
                  <AssertionsSection result={selectedResult} />
                  <JudgeSection result={selectedResult} />
                  <VerdictForm key={selectedResult.id} runId={runId} result={selectedResult} onNextUnreviewed={goToNextUnreviewed} />
                </aside>
              </>
            ) : (
              <div className={styles.panel}>
                <p className="eyebrow">No cases match this filter</p>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  )
}

function CaseRow({ result, selected, onSelect }: { result: EvalResult; selected: boolean; onSelect: () => void }) {
  const passed = result.passed
  return (
    <button type="button" className={styles.caseRow} aria-current={selected} onClick={onSelect}>
      <span className={styles.caseId}>{result.case_id}</span>
      <Chip tone={passed ? 'fit' : 'nofit'}>{passed ? 'pass' : 'fail'}</Chip>
      <span className={styles.caseSnippet}>{result.category}</span>
    </button>
  )
}
