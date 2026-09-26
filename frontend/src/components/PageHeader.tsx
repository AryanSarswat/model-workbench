import type { ReactNode } from 'react'
import styles from './PageHeader.module.css'

// Eyebrow (or breadcrumb) over a serif h1, with optional content below the title and
// actions aligned bottom-right. Pages own the surrounding padding and borders.
export function PageHeader({
  eyebrow,
  title,
  actions,
  className,
  children,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  actions?: ReactNode
  className?: string
  children?: ReactNode
}) {
  return (
    <header className={[styles.header, className].filter(Boolean).join(' ')}>
      <div className={styles.heading}>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className={styles.title}>{title}</h1>
        {children}
      </div>
      {actions && <div className={styles.actions}>{actions}</div>}
    </header>
  )
}
