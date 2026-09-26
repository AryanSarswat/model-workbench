import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../../api/client'
import { getEvalReport, getFeasibility, getModel, listDownloadJobs, listDownloaded, startDownload } from '../../api/endpoints'
import type { DownloadJob, DownloadRequest, DownloadedModelRecord, EvalReportRow, FeasibilityOption, ModelDetail } from '../../api/types'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { LiveDot } from '../../components/LiveDot'
import { PageHeader } from '../../components/PageHeader'
import { ProgressBar } from '../../components/ProgressBar'
import { BACKENDS } from '../../lib/backends'
import { formatCount, formatRelative } from '../../lib/format'
import { GaugeAxisLabels, MemoryGauge } from '../radar/MemoryGauge'
import { VERDICT_CHIP_TONE, VERDICT_LABEL } from '../radar/gauge'
import styles from './ModelPage.module.css'
import {
  bestEvalBackend,
  findActiveGgufJob,
  findActiveSnapshotJob,
  findDownloadedGguf,
  findDownloadedSnapshot,
  optionBackend,
  optionPlaygroundLink,
  optionSizeLabel,
  playgroundLink,
  splitModelId,
} from './modelHelpers'

const FEASIBILITY_STALE_TIME = 10 * 60 * 1000

export default function ModelPage() {
  const { author, name } = useParams()
  const modelId = author && name ? `${author}/${name}` : null

  if (modelId === null) {
    // The route always supplies both segments; this only guards TypeScript's optional params.
    return (
      <main className={styles.main}>
        <PageHeader eyebrow="Radar" title="Model not found" />
      </main>
    )
  }
  return <ModelPageBody modelId={modelId} />
}

function ModelPageBody({ modelId }: { modelId: string }) {
  const queryClient = useQueryClient()

  const modelQuery = useQuery({ queryKey: ['models', modelId], queryFn: () => getModel(modelId) })
  const feasibilityQuery = useQuery({
    queryKey: ['models', modelId, 'feasibility'],
    queryFn: () => getFeasibility(modelId),
    staleTime: FEASIBILITY_STALE_TIME,
  })
  const downloadedQuery = useQuery({ queryKey: ['models', 'downloaded'], queryFn: listDownloaded })
  const activeJobsQuery = useQuery({
    queryKey: ['models', 'downloads', 'active'],
    queryFn: () => listDownloadJobs(true),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      return jobs.some((job) => job.repo_id === modelId) ? 1000 : false
    },
  })
  const evalReportQuery = useQuery({ queryKey: ['evals', 'report'], queryFn: getEvalReport })

  // listDownloadJobs(true) only returns pending/downloading jobs, so a completed download
  // simply disappears from it on the next poll -- invalidate the downloaded-models list so
  // that row flips from "downloading" to "on disk".
  const previousActiveJobIds = useRef<Set<number>>(new Set())
  useEffect(() => {
    const currentIds = new Set((activeJobsQuery.data ?? []).map((job) => job.id))
    const justCompleted = [...previousActiveJobIds.current].some((id) => !currentIds.has(id))
    if (justCompleted) {
      queryClient.invalidateQueries({ queryKey: ['models', 'downloaded'] })
      queryClient.invalidateQueries({ queryKey: ['models', 'downloads', 'active'] })
    }
    previousActiveJobIds.current = currentIds
  }, [activeJobsQuery.data, queryClient])

  const downloadMutation = useMutation({
    mutationFn: (request: DownloadRequest) => startDownload(modelId, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['models', 'downloads', 'active'] }),
  })

  if (modelQuery.isPending) {
    return (
      <main className={styles.main}>
        <p>Loading model…</p>
      </main>
    )
  }
  if (modelQuery.isError) {
    const notFound = modelQuery.error instanceof ApiError && modelQuery.error.code === 'model_not_found'
    return (
      <main className={styles.main}>
        <PageHeader eyebrow="Radar" title={notFound ? 'Model not found' : 'Something went wrong'} />
        {!notFound && <ErrorNotice error={modelQuery.error} />}
      </main>
    )
  }

  const detail = modelQuery.data
  const downloaded = downloadedQuery.data ?? []
  const activeJobs = (activeJobsQuery.data ?? []).filter((job) => job.repo_id === modelId)

  return (
    <main className={styles.main}>
      <ModelHeader detail={detail} downloaded={downloaded} />
      <div className={styles.content}>
        <WaysToRunIt
          modelId={modelId}
          detail={detail}
          feasibilityQuery={feasibilityQuery}
          downloaded={downloaded}
          activeJobs={activeJobs}
          onDownload={(request) => downloadMutation.mutate(request)}
          downloadError={downloadMutation.error}
        />
        <aside className={styles.aside}>
          <DownloadingCard jobs={activeJobs} />
          <EvalHistoryCard modelId={modelId} evalReportQuery={evalReportQuery} />
        </aside>
      </div>
    </main>
  )
}

function ModelHeader({ detail, downloaded }: { detail: ModelDetail; downloaded: DownloadedModelRecord[] }) {
  const { author, name } = splitModelId(detail.id)
  return (
    <header className={styles.header}>
      <div className={styles.heading}>
        <nav aria-label="Breadcrumb" className={['eyebrow', styles.breadcrumb].join(' ')}>
          <Link to="/" className={styles.breadcrumbLink}>
            Radar
          </Link>
          <span>/</span>
          <span>{author}</span>
        </nav>
        <h1 className={styles.title}>{name}</h1>
        <div className={styles.metaRow}>
          <span className={styles.metaId}>{detail.id}</span>
          <span>Released {formatRelative(detail.created_at)}</span>
          <span>{formatCount(detail.downloads)} downloads</span>
          <span>{formatCount(detail.likes)} likes</span>
          <span>{detail.gated ? 'Gated' : 'Not gated'}</span>
        </div>
        <div className={styles.tagsRow}>
          {detail.tags.slice(0, 6).map((tag) => (
            <Chip key={tag} tone="idle">
              {tag}
            </Chip>
          ))}
        </div>
      </div>
      <div className={styles.actions}>
        <a className="btn" href={`https://huggingface.co/${detail.id}`} target="_blank" rel="noreferrer">
          View on Hub
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <path d="M7 3H3v10h10V9M10 3h3v3M13 3L7.5 8.5" />
          </svg>
        </a>
        <Button to={`/evals?model=${encodeURIComponent(detail.id)}`}>Run eval</Button>
        <Button to={playgroundLink(detail.id, downloaded)} variant="solid">
          Open in Playground
        </Button>
      </div>
    </header>
  )
}

function WaysToRunIt({
  modelId,
  detail,
  feasibilityQuery,
  downloaded,
  activeJobs,
  onDownload,
  downloadError,
}: {
  modelId: string
  detail: ModelDetail
  feasibilityQuery: UseQueryResult<{ available_memory_gb: number; options: FeasibilityOption[] }>
  downloaded: DownloadedModelRecord[]
  activeJobs: DownloadJob[]
  onDownload: (request: DownloadRequest) => void
  downloadError: unknown
}) {
  return (
    <section aria-labelledby="ways" className={styles.waysSection}>
      <div className={styles.waysHeader}>
        <h2 id="ways" className={styles.waysTitle}>
          Ways to run it
        </h2>
        {feasibilityQuery.data && (
          <span className={styles.waysSubtitle}>
            Estimated against {feasibilityQuery.data.available_memory_gb.toFixed(1)} GB usable memory
          </span>
        )}
      </div>

      {feasibilityQuery.isPending && <p>Loading feasibility…</p>}
      {feasibilityQuery.isError && <ErrorNotice error={feasibilityQuery.error} />}
      {downloadError != null && <ErrorNotice error={downloadError} />}

      {feasibilityQuery.data && (
        <>
          <div role="row" className={styles.optionsHeaderRow}>
            <div className="eyebrow" role="columnheader">Option</div>
            <div className="eyebrow" role="columnheader">Backend</div>
            <div role="columnheader">
              <GaugeAxisLabels usableMemoryGb={feasibilityQuery.data.available_memory_gb} />
            </div>
            <div className="eyebrow" role="columnheader">Verdict</div>
            <div role="columnheader" />
          </div>

          {feasibilityQuery.data.options.map((option) => (
            <OptionRow
              key={option.label}
              modelId={modelId}
              detail={detail}
              option={option}
              usableMemoryGb={feasibilityQuery.data.available_memory_gb}
              downloaded={downloaded}
              activeJobs={activeJobs}
              onDownload={onDownload}
            />
          ))}
        </>
      )}

      <div role="row" className={styles.optionRow}>
        <div role="cell" className={styles.optionCell}>
          <div className={styles.optionLabel}>Hugging Face Inference API</div>
          <div className={styles.optionReason}>Runs remotely. Works if HF routes this model to an enabled provider.</div>
        </div>
        <div role="cell" className={styles.optionBackend}>api</div>
        <div role="cell" className={styles.optionReason}>No local memory used</div>
        <div role="cell"><Chip tone="idle">Remote</Chip></div>
        <div role="cell" className={styles.actionCell}>
          <Button to={optionPlaygroundLink(modelId, 'api')} className={styles.actionButton}>
            Chat via API
          </Button>
        </div>
      </div>
    </section>
  )
}

function OptionRow({
  modelId,
  detail,
  option,
  usableMemoryGb,
  downloaded,
  activeJobs,
  onDownload,
}: {
  modelId: string
  detail: ModelDetail
  option: FeasibilityOption
  usableMemoryGb: number
  downloaded: DownloadedModelRecord[]
  activeJobs: DownloadJob[]
  onDownload: (request: DownloadRequest) => void
}) {
  const backend = optionBackend(option.label)
  const isSnapshot = backend === 'transformers'
  const filename = option.label

  const onDisk = isSnapshot ? findDownloadedSnapshot(downloaded, modelId) : findDownloadedGguf(downloaded, modelId, filename)
  const activeJob = isSnapshot ? findActiveSnapshotJob(activeJobs, modelId) : findActiveGgufJob(activeJobs, modelId, filename)
  const sizeLabel = optionSizeLabel(option, detail)

  return (
    <div role="row" className={styles.optionRow}>
      <div role="cell" className={styles.optionCell}>
        <div className={styles.optionLabel}>{option.label}</div>
        <div className={styles.optionReason}>{sizeLabel ? `${sizeLabel} · ${option.reason}` : option.reason}</div>
      </div>
      <div role="cell" className={styles.optionBackend}>
        {backend}
      </div>
      <div role="cell">
        <MemoryGauge lo={0} hi={option.estimated_memory_gb} usableMemoryGb={usableMemoryGb} />
      </div>
      <div role="cell">
        <Chip tone={VERDICT_CHIP_TONE[option.verdict]}>{VERDICT_LABEL[option.verdict]}</Chip>
      </div>
      <div role="cell" className={styles.actionCell}>
        {onDisk ? (
          <Button to={optionPlaygroundLink(modelId, backend, filename)} variant="solid" className={styles.actionButton}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M3 8.5l3 3 7-7" />
            </svg>
            On disk · Chat
          </Button>
        ) : activeJob ? (
          <div className={styles.downloadProgress}>
            <span className={styles.downloadPercent}>Downloading {Math.round(activeJob.percent)}%</span>
            <ProgressBar value={activeJob.percent} label={`${option.label} download progress`} height={4} />
          </div>
        ) : (
          <Button className={styles.actionButton} onClick={() => onDownload(isSnapshot ? { snapshot: true } : { filename })}>
            {isSnapshot ? 'Get snapshot' : 'Download'}
          </Button>
        )}
      </div>
    </div>
  )
}

function DownloadingCard({ jobs }: { jobs: DownloadJob[] }) {
  if (jobs.length === 0) return null
  return (
    <section aria-labelledby="dl" className={styles.downloadingCard}>
      <h2 id="dl" className="eyebrow" style={{ margin: 0 }}>
        Downloading
      </h2>
      {jobs.map((job) => (
        <div key={job.id}>
          <div className={styles.downloadingJobHeader}>
            <span className={styles.downloadingFilename}>{job.filename ?? 'snapshot'}</span>
            <LiveDot>job {job.id}</LiveDot>
          </div>
          <ProgressBar value={job.percent} label={`job ${job.id} download progress`} height={6} />
          <div className={styles.downloadingDetail}>
            <span>{job.current_file ?? job.detail}</span>
            <span>{Math.round(job.percent)}%</span>
          </div>
        </div>
      ))}
    </section>
  )
}

function EvalHistoryCard({ modelId, evalReportQuery }: { modelId: string; evalReportQuery: UseQueryResult<EvalReportRow[]> }) {
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
