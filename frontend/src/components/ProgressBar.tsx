import styles from './ProgressBar.module.css'

// Live-red progress bar. `value` is a percentage, 0..100.
export function ProgressBar({ value, label, height = 6 }: { value: number; label: string; height?: number }) {
  const percent = Math.min(100, Math.max(0, value))
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percent)}
      className={styles.track}
      style={{ height }}
    >
      <div className={styles.fill} style={{ width: `${percent}%` }} />
    </div>
  )
}
