import type { ReactNode } from 'react'

export type ChipTone = 'fit' | 'tight' | 'nofit' | 'idle' | 'live'

export function Chip({ tone = 'idle', className, children }: { tone?: ChipTone; className?: string; children: ReactNode }) {
  return <span className={['chip', `v-${tone}`, className].filter(Boolean).join(' ')}>{children}</span>
}
