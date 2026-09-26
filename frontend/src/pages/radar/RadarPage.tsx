import { useQueries, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '../../api/client'
import { discoverModels, getFeasibility } from '../../api/endpoints'
import { useHardware } from '../../api/hooks'
import type { DiscoverSort, DiscoveredModel, FeasibilityReport } from '../../api/types'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Field } from '../../components/Field'
import { PageHeader } from '../../components/PageHeader'
import { SegmentedControl } from '../../components/SegmentedControl'
import { formatCount, formatRelative } from '../../lib/format'
import { GaugeAxisLabels, MemoryGauge } from './MemoryGauge'
import { VERDICT_CHIP_TONE, VERDICT_LABEL, bestVerdict, formatMemoryRange } from './gauge'
import styles from './RadarPage.module.css'

const FEASIBILITY_STALE_TIME = 10 * 60 * 1000

const SORT_OPTIONS: { value: DiscoverSort; label: string }[] = [
  { value: 'trending', label: 'Trending' },
  { value: 'recent', label: 'Recent' },
]

interface Row {
  model: DiscoveredModel
  rank: number
  feasibility: UseQueryResult<FeasibilityReport>
}

function shortFeasibilityError(error: unknown): string {
  if (error instanceof ApiError && error.code === 'feasibility_unknown') return 'No size data available'
  return 'Gated or unavailable'
}

// GGUF / transformers chips derived from a repo's feasibility option labels.
function formatChips(options: FeasibilityReport['options']): string[] {
  const chips: string[] = []
  if (options.some((o) => o.label.toLowerCase().endsWith('.gguf'))) chips.push('GGUF')
  if (options.some((o) => o.label.toLowerCase().startsWith('transformers'))) chips.push('transformers')
  return chips
}

export default function RadarPage() {
  const [sort, setSort] = useState<DiscoverSort>('trending')
  const [filterText, setFilterText] = useState('')

  const hardwareQuery = useHardware()
  const modelsQuery = useQuery({ queryKey: ['models', 'discover', sort], queryFn: () => discoverModels(sort, 20) })
  const models = modelsQuery.data ?? []

  const feasibilityResults = useQueries({
    queries: models.map((model) => ({
      queryKey: ['models', model.id, 'feasibility'],
      queryFn: () => getFeasibility(model.id),
      staleTime: FEASIBILITY_STALE_TIME,
      retry: false,
    })),
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
                className={['field', styles.filterInput].join(' ')}
                placeholder="Model or author"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
              />
            </Field>
            <SegmentedControl label="Sort order" options={SORT_OPTIONS} value={sort} onChange={setSort} />
            <Button aria-label="Refresh from the Hub" onClick={() => void modelsQuery.refetch()}>
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <path d="M13 2.5v4H9M3 13.5v-4h4M12.6 6.5A5 5 0 0 0 3.8 5M3.4 9.5A5 5 0 0 0 12.2 11" />
              </svg>
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
  return (
    <section aria-label="Models" className={styles.table}>
      <div role="row" className={styles.headerRow}>
        <div className="eyebrow" role="columnheader">#</div>
        <div className="eyebrow" role="columnheader">Model</div>
        <div className="eyebrow" role="columnheader">Released</div>
        <div className="eyebrow" role="columnheader">Downloads</div>
        <div className="eyebrow" role="columnheader">Likes</div>
        <div role="columnheader">
          <div className="eyebrow" style={{ marginBottom: 4 }}>Memory needed</div>
          <GaugeAxisLabels usableMemoryGb={usableMemoryGb} />
        </div>
        <div className="eyebrow" role="columnheader">Best option</div>
        <div role="columnheader" />
      </div>

      {rows.map(({ model, rank, feasibility }) => (
        <RadarRow key={model.id} model={model} rank={rank} feasibility={feasibility} usableMemoryGb={usableMemoryGb} />
      ))}

      <footer className={styles.footer}>
        <span className={styles.legendItem}>
          <span className={['seg-fit', styles.swatch].join(' ')} />
          Comfortable, under 70% of memory
        </span>
        <span className={styles.legendItem}>
          <span className={['seg-tight', styles.swatch].join(' ')} />
          Tight, under 95%
        </span>
        <span className={styles.legendItem}>
          <span className={['hatch', styles.swatch].join(' ')} />
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
  return (
    <div role="row" className={styles.row}>
      <div role="cell" className={styles.rank}>
        {String(rank).padStart(2, '0')}
      </div>
      <div role="cell" className={styles.modelCell}>
        <a href={`/models/${model.id}`} className={styles.modelLink}>
          {model.id}
        </a>
        <div className={styles.formatChips}>
          {feasibility.data &&
            formatChips(feasibility.data.options).map((chip) => (
              <Chip key={chip} tone="idle">
                {chip}
              </Chip>
            ))}
        </div>
      </div>
      <div role="cell" className={styles.released}>
        {formatRelative(model.created_at)}
      </div>
      <div role="cell" className={styles.count}>
        {formatCount(model.downloads)}
      </div>
      <div role="cell" className={styles.count}>
        {formatCount(model.likes)}
      </div>
      <div role="cell">
        <FeasibilityGauge feasibility={feasibility} usableMemoryGb={usableMemoryGb} modelId={model.id} />
      </div>
      <div role="cell" className={styles.verdictCell}>
        <FeasibilityVerdict feasibility={feasibility} />
      </div>
      <a href={`/models/${model.id}`} className={['btn', styles.openLink].join(' ')} role="cell">
        Open
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M3 8h10M9 4l4 4-4 4" />
        </svg>
      </a>
    </div>
  )
}

function FeasibilityGauge({
  feasibility,
  usableMemoryGb,
  modelId,
}: {
  feasibility: UseQueryResult<FeasibilityReport>
  usableMemoryGb: number
  modelId: string
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
        <div className={styles.range}>{shortFeasibilityError(feasibility.error)}</div>
      </div>
    )
  }
  const estimates = feasibility.data.options.map((o) => o.estimated_memory_gb)
  const lo = Math.min(...estimates)
  const hi = Math.max(...estimates)
  return (
    <div className={styles.gaugeCell} aria-label={`Memory needed for ${modelId}`}>
      <MemoryGauge lo={lo} hi={hi} usableMemoryGb={usableMemoryGb} />
      <div className={styles.range}>{formatMemoryRange(lo, hi, feasibility.data.options.length)}</div>
    </div>
  )
}

function FeasibilityVerdict({ feasibility }: { feasibility: UseQueryResult<FeasibilityReport> }) {
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
        <span className={styles.note}>{shortFeasibilityError(feasibility.error)}</span>
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
