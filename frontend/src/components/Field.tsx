import type { ReactNode } from 'react'
import styles from './Field.module.css'

// An eyebrow <label> stacked over its control. The child control must carry id={htmlFor};
// give it className="field" for the design's input look.
export function Field({
  label,
  htmlFor,
  className,
  children,
}: {
  label: ReactNode
  htmlFor: string
  className?: string
  children: ReactNode
}) {
  return (
    <div className={[styles.field, className].filter(Boolean).join(' ')}>
      <label htmlFor={htmlFor} className="eyebrow">
        {label}
      </label>
      {children}
    </div>
  )
}
