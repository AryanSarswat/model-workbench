import type { ReactNode } from 'react'
import styles from './LiveDot.module.css'

// Live-red dot with an optional label, e.g. "streaming" or "job 7".
export function LiveDot({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <span className={[styles.live, className].filter(Boolean).join(' ')}>
      <span className={styles.dot} aria-hidden="true" />
      {children}
    </span>
  )
}
