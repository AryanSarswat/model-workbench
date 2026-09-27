import { ApiError } from '../api/client'
import { cx } from '../lib/cx'
import styles from './ErrorNotice.module.css'

// Shows a failed request's message, plus the backend error code for an ApiError.
export function ErrorNotice({ error, className }: { error: unknown; className?: string }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className={cx(styles.notice, className)}>
      <span>{message}</span>
      {error instanceof ApiError && <span className={styles.code}>{error.code}</span>}
    </div>
  )
}
