import { useQueries, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../api/client'
import { discoverModels, modelPath } from '../../api/endpoints'
import { queryKeys, useHardware } from '../../api/hooks'
import type { DiscoverSort, DiscoveredModel, FeasibilityReport } from '../../api/types'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Field } from '../../components/Field'
import { ArrowRightIcon, RefreshIcon } from '../../components/icons'
import { PageHeader } from '../../components/PageHeader'
import { SegmentedControl } from '../../components/SegmentedControl'
import { cx } from '../../lib/cx'
import { formatCount, formatRelative } from '../../lib/format'
import { GaugeAxisLabels, MemoryGauge } from './MemoryGauge'
import { VERDICT_CHIP_TONE, VERDICT_LABEL, bestVerdict, feasibilityQueryOptions, formatMemoryRange, formatThreshold } from './gauge'
import styles from './RadarPage.module.css'

const SORT_OPTIONS: { value: DiscoverSort; label: string }[] = [
  { value: 'trending', label: 'Trending' },
  { value: 'recent', label: 'Recent' },
]

interface Row {
  model: DiscoveredModel
  rank: number
  feasibility: UseQueryResult<FeasibilityReport>
}

// `gated` comes from the model itself, never inferred from the error -- the backend has
// no "gated" error code, so guessing at one would misreport plain network/lookup failures.
function shortFeasibilityError(error: unknown, gated: DiscoveredModel['gated']): string {
  if (gated) return 'Gated'
  if (error instanceof ApiError) {
    if (error.code === 'feasibility_unknown') return 'No size data available'
    if (error.code === 'hf_hub_unreachable') return 'Hub unavailable'
  }
  return 'Unavailable'
}

// GGUF / transformers chips derived from a repo's feasibility option backends.
function formatChips(options: FeasibilityReport['options']): string[] {
  const chips: string[] = []
  if (options.some((o) => o.backend === 'gguf')) chips.push('GGUF')
  if (options.some((o) => o.backend === 'transformers')) chips.push('transformers')
  return chips
}

export default function RadarPage() {
  const [sort, setSort] = useState<DiscoverSort>('trending')
  const [filterText, setFilterText] = useState('')

  const hardwareQuery = useHardware()
  const modelsQuery = useQuery({ queryKey: queryKeys.discoverModels(sort), queryFn: () => discoverModels(sort, 20) })
  const models = modelsQuery.data ?? []

  const feasibilityResults = useQueries({
    queries: models.map((model) => feasibilityQueryOptions(model.id)),
  })

  const filter = filterText.trim().toLowerCase()
  const rows: Row[] = models
    .map((model, index) => ({ model, rank: index + 1, feasibility: feasibilityResults[index] }))
    .filter(
      ({ model }) =>
        filter === '' || model.id.toLowerCase().includes(filter) || (model.author ?? '').toLowerCase().includes(filter),
    )

  return (
    <main className={styles.main}>
      <PageHeader
        eyebrow="Hugging Face Hub · text-generation"
        title="What’s new, and will it run here?"
        actions={
          <div className={styles.controls}>
            <Field label="Filter" htmlFor="filter">
              <input
                id="filter"
                className={cx('field', styles.filterInput)}
                placeholder="Model or author"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
              />
            </Field>
            <SegmentedControl label="Sort order" options={SORT_OPTIONS} value={sort} onChange={setSort} />
            <Button aria-label="Refresh from the Hub" onClick={() => void modelsQuery.refetch()}>
              <RefreshIcon size={15} />
            </Button>
          </div>
        }
      />

      {hardwareQuery.isError && <ErrorNotice error={hardwareQuery.error} />}
      {modelsQuery.isPending && <p>Loading models…</p>}
      {modelsQuery.isError && <ErrorNotice error={modelsQuery.error} />}

      {hardwareQuery.data && modelsQuery.data && (
        <RadarTable usableMemoryGb={hardwareQuery.data.usable_memory_gb} rows={rows} />
      )}
    </main>
  )
}

function RadarTable({ usableMemoryGb, rows }: { usableMemoryGb: number; rows: Row[] }) {
  // Every report carries the same thresholds; the legend shows them once any row has loaded.
  const thresholds = rows.find((row) => row.feasibility.data)?.feasibility.data
  return (
    <section aria-label="Models" className={styles.table}>
      <div className={styles.headerRow}>
        <div className="eyebrow">#</div>
        <div className="eyebrow">Model</div>
        <div className="eyebrow">Released</div>
        <div className="eyebrow">Downloads</div>
        <div className="eyebrow">Likes</div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 4 }}>Memory needed</div>
          <GaugeAxisLabels usableMemoryGb={usableMemoryGb} />
        </div>
        <div className="eyebrow">Best option</div>
        <div />
      </div>

      {rows.map(({ model, rank, feasibility }) => (
        <RadarRow key={model.id} model={model} rank={rank} feasibility={feasibility} usableMemoryGb={usableMemoryGb} />
      ))}

      <footer className={styles.footer}>
        <span className={styles.legendItem}>
          <span className={cx('seg-fit', styles.swatch)} />
          Comfortable{thresholds && `, under ${formatThreshold(thresholds.comfortable_fraction)} of memory`}
        </span>
        <span className={styles.legendItem}>
          <span className={cx('seg-tight', styles.swatch)} />
          Tight{thresholds && `, under ${formatThreshold(thresholds.tight_fraction)}`}
        </span>
        <span className={styles.legendItem}>
          <span className={cx('hatch', styles.swatch)} />
          Won’t fit
        </span>
        <span className={styles.legendNote}>
          Bar spans a repo’s smallest to largest option. File size or params × dtype, plus 20% for KV cache. Advisory
          only.
        </span>
      </footer>
    </section>
  )
}

function RadarRow({
  model,
  rank,
  feasibility,
  usableMemoryGb,
}: {
  model: DiscoveredModel
  rank: number
  feasibility: UseQueryResult<FeasibilityReport>
  usableMemoryGb: number
}) {
  const href = `/models/${modelPath(model.id)}`
  const errorLabel = feasibility.isError ? shortFeasibilityError(feasibility.error, model.gated) : null

  return (
    <div className={styles.row}>
      <div className={styles.rank}>{String(rank).padStart(2, '0')}</div>
      <div className={styles.modelCell}>
        <Link to={href} className={styles.modelLink}>
          {model.id}
        </Link>
        <div className={styles.formatChips}>
          {feasibility.data &&
            formatChips(feasibility.data.options).map((chip) => (
              <Chip key={chip} tone="idle">
                {chip}
              </Chip>
            ))}
        </div>
      </div>
      <div className={styles.released}>{formatRelative(model.created_at)}</div>
      <div className={styles.count}>{formatCount(model.downloads)}</div>
      <div className={styles.count}>{formatCount(model.likes)}</div>
      <div>
        <FeasibilityGauge feasibility={feasibility} usableMemoryGb={usableMemoryGb} errorLabel={errorLabel} />
      </div>
      <div className={styles.verdictCell}>
        <FeasibilityVerdict feasibility={feasibility} errorLabel={errorLabel} />
      </div>
      <Button to={href} className={styles.openLink}>
        Open
        <ArrowRightIcon />
      </Button>
    </div>
  )
}

function FeasibilityGauge({
  feasibility,
  usableMemoryGb,
  errorLabel,
}: {
  feasibility: UseQueryResult<FeasibilityReport>
  usableMemoryGb: number
  errorLabel: string | null
}) {
  if (feasibility.isPending) {
    return (
      <div className={styles.gaugeCell}>
        <div style={{ height: 10, background: 'var(--track)' }} aria-hidden="true" />
        <div className={styles.range}>reading repo files…</div>
      </div>
    )
  }
  if (feasibility.isError) {
    return (
      <div className={styles.gaugeCell}>
        <div style={{ height: 10, background: 'var(--track)' }} aria-hidden="true" />
        <div className={styles.range}>{errorLabel}</div>
      </div>
    )
  }
  const estimates = feasibility.data.options.map((o) => o.estimated_memory_gb)
  const lo = Math.min(...estimates)
  const hi = Math.max(...estimates)
  return (
    <div className={styles.gaugeCell}>
      <MemoryGauge lo={lo} hi={hi} usableMemoryGb={usableMemoryGb} thresholds={feasibility.data} />
      <div className={styles.range}>{formatMemoryRange(lo, hi, feasibility.data.options.length)}</div>
    </div>
  )
}

function FeasibilityVerdict({
  feasibility,
  errorLabel,
}: {
  feasibility: UseQueryResult<FeasibilityReport>
  errorLabel: string | null
}) {
  if (feasibility.isPending) {
    return (
      <>
        <Chip tone="idle">Estimating</Chip>
        <span className={styles.note}>reading repo files…</span>
      </>
    )
  }
  if (feasibility.isError) {
    return (
      <>
        <Chip tone="idle">Unknown</Chip>
        <span className={styles.note}>{errorLabel}</span>
      </>
    )
  }
  const verdicts = feasibility.data.options.map((o) => o.verdict)
  const verdict = bestVerdict(verdicts)
  if (verdict === null) {
    return (
      <>
        <Chip tone="idle">Unknown</Chip>
        <span className={styles.note}>No runnable options</span>
      </>
    )
  }
  const fitCount = verdicts.filter((v) => v === 'comfortable').length
  const tightCount = verdicts.filter((v) => v === 'tight').length
  return (
    <>
      <Chip tone={VERDICT_CHIP_TONE[verdict]}>{VERDICT_LABEL[verdict]}</Chip>
      <span className={styles.note}>
        {fitCount} fit · {tightCount} tight
      </span>
    </>
  )
}
