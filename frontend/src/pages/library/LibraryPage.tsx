import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import {
  deleteDownloaded,
  listDownloadJobs,
  listDownloaded,
  listTools,
  reloadTools,
  setHfKey,
} from '../../api/endpoints'
import { queryKeys, useHardware, useHfKeyStatus } from '../../api/hooks'
import type { DownloadedModelRecord } from '../../api/types'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Field } from '../../components/Field'
import { ProgressBar } from '../../components/ProgressBar'
import { formatGb, formatRelative } from '../../lib/format'
import styles from './LibraryPage.module.css'
import { chatPath, formatChip, gpuLabel, summarizeParams } from './libraryFormat'

const DOWNLOADED_KEY = ['library', 'downloaded']
const DOWNLOAD_JOBS_KEY = ['library', 'downloadJobs']
const TOOLS_KEY = ['library', 'tools']

export default function LibraryPage() {
  const queryClient = useQueryClient()

  const downloadedQuery = useQuery({ queryKey: DOWNLOADED_KEY, queryFn: listDownloaded })
  const jobsQuery = useQuery({
    queryKey: DOWNLOAD_JOBS_KEY,
    queryFn: () => listDownloadJobs(true),
    refetchInterval: (query) => ((query.state.data?.length ?? 0) > 0 ? 1000 : false),
  })
  const toolsQuery = useQuery({ queryKey: TOOLS_KEY, queryFn: listTools })

  // A job disappearing from the active list (poll above) means it finished or failed --
  // either way the downloaded-models table may have changed underneath it.
  const previousJobIdsRef = useRef<Set<number>>(new Set())
  useEffect(() => {
    const currentIds = new Set((jobsQuery.data ?? []).map((job) => job.id))
    const completed = [...previousJobIdsRef.current].some((id) => !currentIds.has(id))
    if (completed) void queryClient.invalidateQueries({ queryKey: DOWNLOADED_KEY })
    previousJobIdsRef.current = currentIds
  }, [jobsQuery.data, queryClient])

  const downloaded = downloadedQuery.data ?? []
  const jobs = jobsQuery.data ?? []
  const tools = toolsQuery.data ?? []
  const totalGb = downloaded.reduce((sum, d) => sum + d.size_bytes, 0) / 1024 ** 3

  const deleteMutation = useMutation({
    mutationFn: deleteDownloaded,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: DOWNLOADED_KEY }),
  })

  function handleDelete(record: DownloadedModelRecord) {
    if (!window.confirm(`Delete "${record.repo_id}" from disk?`)) return
    deleteMutation.mutate(record.id)
  }

  const [reloadStatus, setReloadStatus] = useState<string | null>(null)
  const reloadMutation = useMutation({
    mutationFn: reloadTools,
    onSuccess: (result) => {
      setReloadStatus(`Reloaded ${result.count} tool${result.count === 1 ? '' : 's'}`)
      void queryClient.invalidateQueries({ queryKey: TOOLS_KEY })
    },
  })

  return (
    <main className={styles.page}>
      <div className={styles.main}>
        <header className={styles.header}>
          <div className="eyebrow">Everything local to this machine</div>
          <h1 className={styles.title}>Library</h1>
        </header>

        <section aria-labelledby="disk" className={styles.section}>
          <div className={styles.sectionHead}>
            <h2 id="disk" className={styles.h2}>
              On disk
            </h2>
            <span className={styles.meta}>
              {downloaded.length} model{downloaded.length === 1 ? '' : 's'} · {totalGb.toFixed(1)} GB
            </span>
          </div>
          <div className={[styles.diskRow, styles.diskHeadRow].join(' ')}>
            <div className="eyebrow">Model</div>
            <div className="eyebrow">Format</div>
            <div className="eyebrow">Size</div>
            <div className="eyebrow">Last used</div>
            <div />
          </div>
          {downloadedQuery.isError && <ErrorNotice error={downloadedQuery.error} />}
          {deleteMutation.isError && <ErrorNotice error={deleteMutation.error} />}
          {downloaded.length === 0 && jobs.length === 0 && (
            <p className={styles.empty}>Nothing downloaded yet. Find a model on the Radar tab.</p>
          )}
          {downloaded.map((record) => (
            <div key={record.id} className={styles.diskRow}>
              <Link to={`/models/${record.repo_id}`} className={styles.repoLink}>
                {record.repo_id}
              </Link>
              <span>
                <Chip tone="idle">{formatChip(record)}</Chip>
              </span>
              <span className={styles.size}>{formatGb(record.size_bytes)}</span>
              <span className={styles.lastUsed}>{formatRelative(record.last_used_at ?? record.downloaded_at)}</span>
              <div className={styles.rowActions}>
                <Button to={chatPath(record)}>Chat</Button>
                <button
                  type="button"
                  aria-label={`Delete ${record.repo_id}`}
                  className={styles.iconButton}
                  onClick={() => handleDelete(record)}
                >
                  <TrashIcon />
                </button>
              </div>
            </div>
          ))}
          {jobs.map((job) => (
            <div key={job.id} className={styles.diskRow}>
              <span className={styles.repoLink}>{job.repo_id}</span>
              <span className={styles.size}>{job.filename ?? job.current_file ?? 'snapshot'}</span>
              <span />
              <div className={styles.progressCell}>
                <ProgressBar value={job.percent} label={`${job.repo_id} download progress`} />
                <span>{Math.round(job.percent)}%</span>
              </div>
            </div>
          ))}
        </section>

        <section aria-labelledby="tools" className={styles.section}>
          <div className={styles.sectionHead}>
            <div className={styles.sectionHeadLeft}>
              <h2 id="tools" className={styles.h2}>
                Tools
              </h2>
              <span className={styles.meta}>backend/app/tools/ · {tools.length} loaded</span>
              {reloadStatus && <span className={styles.reloadStatus}>{reloadStatus}</span>}
            </div>
            <Button onClick={() => reloadMutation.mutate()} disabled={reloadMutation.isPending}>
              <ReloadIcon /> Reload
            </Button>
          </div>
          {toolsQuery.isError && <ErrorNotice error={toolsQuery.error} />}
          {reloadMutation.isError && <ErrorNotice error={reloadMutation.error} />}
          {tools.map((tool) => (
            <div key={tool.name} className={styles.toolRow}>
              <span className={styles.toolName}>{tool.name}</span>
              <span className={styles.toolDesc}>{tool.description}</span>
              <span className={styles.toolArgs}>{summarizeParams(tool)}</span>
            </div>
          ))}
          <p className={styles.toolsFooter}>
            To add one, drop a file with a <code>TOOL_SPEC</code> and <code>run()</code> into the folder, list it in{' '}
            <code>_TOOL_MODULE_NAMES</code>, then Reload.
          </p>
        </section>
      </div>

      <aside className={styles.aside}>
        <HfKeyCard />
        <MachineCard />
      </aside>
    </main>
  )
}

function HfKeyCard() {
  const queryClient = useQueryClient()
  const { data } = useHfKeyStatus()
  const [key, setKey] = useState('')

  const mutation = useMutation({
    mutationFn: setHfKey,
    onSuccess: () => {
      setKey('')
      void queryClient.invalidateQueries({ queryKey: queryKeys.hfKeyStatus })
    },
  })

  return (
    <section aria-labelledby="key" className={styles.card}>
      <h2 id="key" className={[styles.h2, styles.cardTitle].join(' ')}>
        Hugging Face API key
      </h2>
      <Field label="Token" htmlFor="hfkey">
        <div className={styles.keyRow}>
          <input
            id="hfkey"
            type="password"
            className={['field', styles.keyInput].join(' ')}
            placeholder="hf_…"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <Button onClick={() => mutation.mutate(key)} disabled={!key.trim() || mutation.isPending}>
            Save
          </Button>
        </div>
      </Field>
      <p className={styles.note}>
        {data?.is_set ? 'Set' : 'Not set'}. Stored in backend/.env, never in the database or logs.
      </p>
      {mutation.isError && <ErrorNotice error={mutation.error} />}
    </section>
  )
}

function MachineCard() {
  const { data, isError } = useHardware()
  return (
    <section aria-labelledby="machine" className={styles.machine}>
      <h2 id="machine" className={[styles.h2, styles.machineTitle].join(' ')}>
        This machine
      </h2>
      {isError && <ErrorNotice error={new Error('Hardware detection unavailable')} />}
      {data && (
        <dl className={styles.dl}>
          <dt className={styles.dt}>Platform</dt>
          <dd className={styles.dd}>
            {data.platform} · {data.arch}
          </dd>
          <dt className={styles.dt}>GPU</dt>
          <dd className={styles.dd}>{gpuLabel(data.gpu)}</dd>
          {data.gpu.vram_gb != null && (
            <>
              <dt className={styles.dt}>VRAM</dt>
              <dd className={styles.dd}>{data.gpu.vram_gb.toFixed(1)} GB</dd>
            </>
          )}
          <dt className={styles.dt}>Total RAM</dt>
          <dd className={styles.dd}>{data.total_ram_gb.toFixed(1)} GB</dd>
          <dt className={styles.dt}>Usable</dt>
          <dd className={styles.dd}>{data.usable_memory_gb.toFixed(1)} GB</dd>
        </dl>
      )}
      <p className={styles.thresholdNote}>Fit verdicts: comfortable under 70% of usable memory, tight under 95%.</p>
    </section>
  )
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M2.5 4h11M6 4V2.5h4V4M4 4l.8 9.5h6.4L12 4" />
    </svg>
  )
}

function ReloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M13 2.5v4H9M3 13.5v-4h4M12.6 6.5A5 5 0 0 0 3.8 5M3.4 9.5A5 5 0 0 0 12.2 11" />
    </svg>
  )
}
