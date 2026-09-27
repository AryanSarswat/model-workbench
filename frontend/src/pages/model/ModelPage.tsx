import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useParams } from 'react-router'
import { ApiError } from '../../api/client'
import { getEvalReport, getModel, startDownload } from '../../api/endpoints'
import { isActiveJob, useDownloadedModels, useDownloadJobs } from '../../api/hooks'
import type { DownloadRequest } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { PageHeader } from '../../components/PageHeader'
import { feasibilityQueryOptions } from '../radar/gauge'
import styles from './ModelPage.module.css'
import { DownloadingCard } from './DownloadingCard'
import { EvalHistoryCard } from './EvalHistoryCard'
import { ModelHeader } from './ModelHeader'
import { WaysToRunIt, type FailedDownload } from './WaysToRunIt'

export default function ModelPage() {
  // The splat is the whole Hub id: "Qwen/Qwen3-14B", or just "gpt2" for author-less repos.
  const modelId = useParams()['*'] || null

  if (modelId === null) {
    return (
      <main className={styles.main}>
        <PageHeader eyebrow="Radar" title="Model not found" />
      </main>
    )
  }
  return <ModelPageBody modelId={modelId} />
}

function ModelPageBody({ modelId }: { modelId: string }) {

  const modelQuery = useQuery({ queryKey: ['models', modelId], queryFn: () => getModel(modelId) })
  const feasibilityQuery = useQuery(feasibilityQueryOptions(modelId))
  const downloadedQuery = useDownloadedModels()
  const evalReportQuery = useQuery({ queryKey: ['evals', 'report'], queryFn: getEvalReport })

  // useDownloadJobs refreshes the downloaded list when a job completes, flipping its row
  // to "on disk"; a failed one stays listed with its error.
  const allJobs = useDownloadJobs()
  const modelJobs = useMemo(() => allJobs.filter((job) => job.repo_id === modelId), [allJobs, modelId])
  const modelActiveJobs = useMemo(() => modelJobs.filter(isActiveJob), [modelJobs])
  const failedDownloads = useMemo<FailedDownload[]>(
    () =>
      modelJobs
        .filter((job) => job.status === 'failed')
        .map((job) => ({ id: job.id, message: `${job.filename ?? 'snapshot'}: ${job.error ?? 'Download failed.'}` })),
    [modelJobs],
  )

  const downloadMutation = useMutation({
    mutationFn: (request: DownloadRequest) => startDownload(modelId, request),
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

  return (
    <main className={styles.main}>
      <ModelHeader detail={detail} downloaded={downloaded} />
      <div className={styles.content}>
        <WaysToRunIt
          modelId={modelId}
          detail={detail}
          feasibilityQuery={feasibilityQuery}
          downloaded={downloaded}
          activeJobs={modelActiveJobs}
          onDownload={(request) => downloadMutation.mutate(request)}
          downloadPending={downloadMutation.isPending}
          downloadError={downloadMutation.error}
          failedDownloads={failedDownloads}
        />
        <aside className={styles.aside}>
          <DownloadingCard jobs={modelActiveJobs} />
          <EvalHistoryCard modelId={modelId} evalReportQuery={evalReportQuery} />
        </aside>
      </div>
    </main>
  )
}

