import { Link } from 'react-router'
import type { DownloadedModelRecord, ModelDetail } from '../../api/types'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { formatCount, formatRelative } from '../../lib/format'
import styles from './ModelPage.module.css'
import { playgroundLink, splitModelId } from './modelHelpers'

export function ModelHeader({ detail, downloaded }: { detail: ModelDetail; downloaded: DownloadedModelRecord[] }) {
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
