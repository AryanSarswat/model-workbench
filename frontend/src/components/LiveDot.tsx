import type { ReactNode } from 'react'
import { cx } from '../lib/cx'
import styles from './LiveDot.module.css'

// Live-red dot with an optional label, e.g. "streaming" or "job 7".
export function LiveDot({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <span className={cx(styles.live, className)}>
      <span className={styles.dot} aria-hidden="true" />
      {children}
    </span>
  )
}
