import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Field } from '../../components/Field'
import { LiveDot } from '../../components/LiveDot'
import { PageHeader } from '../../components/PageHeader'
import { ProgressBar } from '../../components/ProgressBar'
import type { BackendName } from '../../api/types'
import { BACKENDS, BACKEND_NAMES, type BackendInfo } from '../../lib/backends'
import type { ActiveEvalRun } from './activeRun'
import { aggregateReport, type EvalMatrix, type MatrixCell } from './aggregateReport'
import styles from './EvalsPage.module.css'
import { useActiveEvalRun, useDatasetCategories, useDownloadedModels, useEvalReport, useStartEvalRun } from './queries'
import { buildRunRequest, modelIdSuggestions, sortedCategories, type RunFormState } from './runForm'

export default function EvalsPage() {
  const reportQuery = useEvalReport()
  const activeRunQuery = useActiveEvalRun()

  const matrix = reportQuery.data ? aggregateReport(reportQuery.data) : null
  const eyebrow = matrix
    ? `${matrix.categories.reduce((sum, c) => sum + c.cases, 0)} cases · ${matrix.categories.length} categories · latest run per model and backend`
    : 'Evals'

  return (
    <main className={styles.page}>
      <PageHeader eyebrow={eyebrow} title="How they compare" actions={<RunForm activeRun={activeRunQuery.data ?? null} />} />

      {activeRunQuery.data && <RunningStrip activeRun={activeRunQuery.data} />}

      {reportQuery.isPending && <p className="eyebrow">Loading…</p>}
      {reportQuery.isError && <ErrorNotice error={reportQuery.error} />}
      {matrix && <ComparisonMatrix matrix={matrix} />}

      {matrix && matrix.rows.length > 0 && (
        <p className={styles.footnote}>
          Cell shade tracks pass rate. JSON output reliability is at (or near) 100% where the backend enforces the
          schema (llama.cpp grammar, transformers guided generation); API runs rely on prompting and retrying, so
          it's best-effort. Tool-call reliability counts cases where the expected tool was called without exhausting
          retries.
        </p>
      )}
    </main>
  )
}

function RunForm({ activeRun }: { activeRun: ActiveEvalRun | null }) {
  const [searchParams] = useSearchParams()
  const [form, setForm] = useState<RunFormState>({
    modelId: searchParams.get('model') ?? '',
    backend: 'api',
    category: '',
    judgeModelId: '',
  })

  const downloadedQuery = useDownloadedModels()
  const reportQuery = useEvalReport()
  const categoriesQuery = useDatasetCategories()
  const startRun = useStartEvalRun()

  const modelSuggestions = modelIdSuggestions(form.backend, downloadedQuery.data ?? [], reportQuery.data ?? [])
  const categories = sortedCategories(categoriesQuery.data ?? [])
  const alreadyRunning = activeRun?.status === 'streaming'

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (form.modelId.trim() === '') return
    startRun.mutate(buildRunRequest(form))
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <Field label="Model" htmlFor="run-model">
        <input
          id="run-model"
          className={`field ${styles.modelField}`}
          list="run-model-suggestions"
          value={form.modelId}
          onChange={(e) => setForm({ ...form, modelId: e.target.value })}
          placeholder="org/model-name"
        />
        <datalist id="run-model-suggestions">
          {modelSuggestions.map((id) => (
            <option key={id} value={id} />
          ))}
        </datalist>
      </Field>
      <Field label="Backend" htmlFor="run-backend">
        <select
          id="run-backend"
          className={`field ${styles.backendField}`}
          value={form.backend}
          onChange={(e) => setForm({ ...form, backend: e.target.value as BackendName })}
        >
          {BACKEND_NAMES.map((name) => (
            <option key={name} value={name}>
              {BACKENDS[name].label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Category" htmlFor="run-category">
        <select
          id="run-category"
          className={`field ${styles.field}`}
          value={form.category}
          onChange={(e) => setForm({ ...form, category: e.target.value })}
        >
          <option value="">All categories</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Judge model id" htmlFor="run-judge">
        <input
          id="run-judge"
          className={`field ${styles.judgeField}`}
          value={form.judgeModelId}
          onChange={(e) => setForm({ ...form, judgeModelId: e.target.value })}
          placeholder="optional"
        />
      </Field>
      <button type="submit" className="btn btn-solid" disabled={startRun.isPending || alreadyRunning}>
        Run eval
      </button>
      {alreadyRunning && <p className={styles.formNote}>A run is already in progress.</p>}
      {startRun.isError && <ErrorNotice error={startRun.error} />}
    </form>
  )
}

function RunningStrip({ activeRun }: { activeRun: ActiveEvalRun }) {
  if (activeRun.status === 'error') {
    return <ErrorNotice error={new Error(activeRun.error ?? 'The eval run failed.')} />
  }
  if (activeRun.status === 'done') {
    return (
      <section aria-label="Finished run" className={styles.finished}>
        <span>
          Finished · <strong>{activeRun.request.model_id}</strong> · {BACKENDS[activeRun.request.backend ?? 'api'].label}
        </span>
        {activeRun.runId != null && (
          <Link to={`/evals/runs/${activeRun.runId}`} className={styles.watchLink}>
            View results
          </Link>
        )}
      </section>
    )
  }
  if (activeRun.event == null) return null
  const { event, request, runId } = activeRun
  const percent = event.total > 0 ? (event.completed / event.total) * 100 : 0
  return (
    <section aria-label="Running" className={styles.running}>
      <LiveDot>RUNNING</LiveDot>
      <span className={styles.runningMeta}>
        <strong>{request.model_id}</strong> · {BACKENDS[request.backend ?? 'api'].label} · {request.category ?? 'all categories'}
        {event.current_case && (
          <>
            {' '}
            · now on <strong>{event.current_case}</strong>
          </>
        )}
      </span>
      <div className={styles.runningProgress}>
        <ProgressBar value={percent} label="Eval run progress" />
        <span className={styles.tokValue}>
          {event.completed} / {event.total}
        </span>
      </div>
      {runId != null ? (
        <Link to={`/evals/runs/${runId}`} className={styles.watchLink}>
          Watch results
        </Link>
      ) : (
        <span className={styles.formNote}>Resolving run…</span>
      )}
    </section>
  )
}

function ComparisonMatrix({ matrix }: { matrix: EvalMatrix }) {
  if (matrix.rows.length === 0) {
    return <p className="eyebrow">No eval runs yet</p>
  }
  const gridTemplateColumns = `minmax(0, 1fr) repeat(${matrix.categories.length}, 104px) 96px 76px 118px 118px`

  return (
    <section aria-label="Comparison" className={styles.matrix}>
      <div className={styles.matrixHead} style={{ gridTemplateColumns }}>
        <div className="eyebrow">Model · backend</div>
        {matrix.categories.map((category) => (
          <div key={category.name} className="eyebrow">
            {category.name}
            <br />
            {category.cases}
          </div>
        ))}
        <div className="eyebrow" style={{ color: 'var(--ink)' }}>
          Overall ↓
        </div>
        <div className="eyebrow">tok/s</div>
        <div className="eyebrow">Tool calls</div>
        <div className="eyebrow">JSON output</div>
      </div>

      {matrix.rows.map((row) => (
        <div key={`${row.modelId}\u0000${row.backend}`} className={styles.row} style={{ gridTemplateColumns }}>
          <div className={styles.rowHead}>
            <Link to={`/evals/runs/${row.latestRunId}`} className={styles.modelId}>
              {row.modelId}
            </Link>
            <span>
              <Chip tone="idle">{BACKENDS[row.backend].label}</Chip>
            </span>
          </div>
          {row.cells.map((cell, i) => (
            <MatrixCellView key={matrix.categories[i].name} cell={cell} />
          ))}
          <div className={styles.overall}>{row.overallPct}%</div>
          <div className={styles.tokValue}>{row.tokensPerSec != null ? row.tokensPerSec.toFixed(1) : '—'}</div>
          <MetricBar value={row.toolCallReliability} />
          <MetricBar value={row.structuredOutputReliability} modeWord={modeWord(BACKENDS[row.backend].structuredOutputMode)} />
        </div>
      ))}
    </section>
  )
}

function MatrixCellView({ cell }: { cell: MatrixCell | null }) {
  return (
    <div className={styles.cell} style={cell ? { background: `rgba(37, 94, 140, ${cell.tint.toFixed(2)})` } : undefined}>
      <span className={styles.cellPct}>{cell ? `${cell.pct}%` : '—'}</span>
      <span className={styles.cellCount}>{cell ? `${cell.passed}/${cell.cases}` : 'not run'}</span>
    </div>
  )
}

function MetricBar({ value, modeWord: mode }: { value: number | null; modeWord?: string }) {
  if (value == null) {
    return (
      <div className={styles.metric}>
        <span className={styles.metricValue}>—</span>
      </div>
    )
  }
  const pct = Math.round(value * 100)
  return (
    <div className={styles.metric}>
      <span className={styles.metricValue}>
        {pct}% {mode && <span className={styles.modeWord}>{mode}</span>}
      </span>
      <div className={styles.barTrack}>
        <div className={styles.barFill} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function modeWord(mode: BackendInfo['structuredOutputMode']): string {
  return mode === 'prompt_retry' ? 'retry' : mode
}
