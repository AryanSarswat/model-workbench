import type { ReactNode } from 'react'
import styles from './SegmentedControl.module.css'

export interface SegmentOption<T extends string> {
  value: T
  label: ReactNode
}

// A group of aria-pressed toggle buttons (Trending/Recent, backend picker). Name the
// group with `label` (aria-label) or `labelledBy` (id of a visible label). `mono`
// is the backend-picker style.
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  labelledBy,
  mono = false,
}: {
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
  label?: string
  labelledBy?: string
  mono?: boolean
}) {
  return (
    <div role="group" aria-label={label} aria-labelledby={labelledBy} className={styles.group}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          className={[styles.segment, mono && styles.mono].filter(Boolean).join(' ')}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
