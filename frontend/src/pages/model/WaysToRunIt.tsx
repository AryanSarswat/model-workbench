import { type UseQueryResult } from '@tanstack/react-query'
import type { DownloadJob, DownloadRequest, DownloadedModelRecord, FeasibilityOption, FeasibilityReport, ModelDetail } from '../../api/types'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { ProgressBar } from '../../components/ProgressBar'
import { GaugeAxisLabels, MemoryGauge } from '../radar/MemoryGauge'
import { VERDICT_CHIP_TONE, VERDICT_LABEL } from '../radar/gauge'
import styles from './ModelPage.module.css'
import { findActiveGgufJob, findActiveSnapshotJob, findDownloadedGguf, findDownloadedSnapshot, optionBackend, optionPlaygroundLink, optionSizeLabel } from './modelHelpers'

export interface FailedDownload {
  id: number
  message: string
}

export function WaysToRunIt({
  modelId,
  detail,
  feasibilityQuery,
  downloaded,
  activeJobs,
  onDownload,
  downloadPending,
  downloadError,
  failedDownloads,
}: {
  modelId: string
  detail: ModelDetail
  feasibilityQuery: UseQueryResult<FeasibilityReport>
  downloaded: DownloadedModelRecord[]
  activeJobs: DownloadJob[]
  onDownload: (request: DownloadRequest) => void
  downloadPending: boolean
  downloadError: unknown
  failedDownloads: FailedDownload[]
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
      {failedDownloads.map((failed) => (
        <ErrorNotice key={failed.id} error={new Error(failed.message)} />
      ))}

      {feasibilityQuery.data && (
        <>
          <div className={styles.optionsHeaderRow}>
            <div className="eyebrow">Option</div>
            <div className="eyebrow">Backend</div>
            <div>
              <GaugeAxisLabels usableMemoryGb={feasibilityQuery.data.available_memory_gb} />
            </div>
            <div className="eyebrow">Verdict</div>
            <div />
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
              downloadPending={downloadPending}
            />
          ))}
        </>
      )}

      <div className={styles.optionRow}>
        <div className={styles.optionCell}>
          <div className={styles.optionLabel}>Hugging Face Inference API</div>
          <div className={styles.optionReason}>Runs remotely. Works if HF routes this model to an enabled provider.</div>
        </div>
        <div className={styles.optionBackend}>api</div>
        <div className={styles.optionReason}>No local memory used</div>
        <div><Chip tone="idle">Remote</Chip></div>
        <div className={styles.actionCell}>
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
  downloadPending,
}: {
  modelId: string
  detail: ModelDetail
  option: FeasibilityOption
  usableMemoryGb: number
  downloaded: DownloadedModelRecord[]
  activeJobs: DownloadJob[]
  onDownload: (request: DownloadRequest) => void
  downloadPending: boolean
}) {
  const backend = optionBackend(option.label)
  const isSnapshot = backend === 'transformers'
  const filename = option.label

  const onDisk = isSnapshot ? findDownloadedSnapshot(downloaded, modelId) : findDownloadedGguf(downloaded, modelId, filename)
  const activeJob = isSnapshot ? findActiveSnapshotJob(activeJobs, modelId) : findActiveGgufJob(activeJobs, modelId, filename)
  const sizeLabel = optionSizeLabel(option, detail)

  return (
    <div className={styles.optionRow}>
      <div className={styles.optionCell}>
        <div className={styles.optionLabel}>{option.label}</div>
        <div className={styles.optionReason}>{sizeLabel ? `${sizeLabel} · ${option.reason}` : option.reason}</div>
      </div>
      <div className={styles.optionBackend}>{backend}</div>
      <div>
        <MemoryGauge lo={0} hi={option.estimated_memory_gb} usableMemoryGb={usableMemoryGb} />
      </div>
      <div>
        <Chip tone={VERDICT_CHIP_TONE[option.verdict]}>{VERDICT_LABEL[option.verdict]}</Chip>
      </div>
      <div className={styles.actionCell}>
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
          <Button
            className={styles.actionButton}
            disabled={downloadPending}
            onClick={() => onDownload(isSnapshot ? { snapshot: true } : { filename })}
          >
            {isSnapshot ? 'Get snapshot' : 'Download'}
          </Button>
        )}
      </div>
    </div>
  )
}
