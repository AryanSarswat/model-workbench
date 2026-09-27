import type { ReactNode } from 'react'
import { cx } from '../lib/cx'

export type ChipTone = 'fit' | 'tight' | 'nofit' | 'idle' | 'live'

export function Chip({ tone = 'idle', className, children }: { tone?: ChipTone; className?: string; children: ReactNode }) {
  return <span className={cx('chip', `v-${tone}`, className)}>{children}</span>
}
