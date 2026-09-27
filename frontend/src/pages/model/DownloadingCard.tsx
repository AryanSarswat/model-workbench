import type { DownloadJob } from '../../api/types'
import { LiveDot } from '../../components/LiveDot'
import { ProgressBar } from '../../components/ProgressBar'
import styles from './ModelPage.module.css'

export function DownloadingCard({ jobs }: { jobs: DownloadJob[] }) {
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
