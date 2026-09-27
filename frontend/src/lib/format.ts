const DASH = '—'

const compact = new Intl.NumberFormat('en', { notation: 'compact' })

// 640, 1.4K, 612K, 1.2M
export function formatCount(n: number | null | undefined): string {
  return n == null ? DASH : compact.format(n)
}

// Bytes as GB with one decimal, using 1024^3 like the backend's memory figures.
export function formatGb(bytes: number | null | undefined): string {
  return bytes == null ? DASH : `${(bytes / 1024 ** 3).toFixed(1)} GB`
}

// "today", "1 day ago", "5 days ago", "3 wk ago", "2 mo ago"
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return DASH
  const days = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000))
  if (days === 0) return 'today'
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`
  if (days < 30) return `${Math.round(days / 7)} wk ago`
  return `${Math.round(days / 30)} mo ago`
}

// 14_800_000_000 -> "14.8B params"
export function formatParamCount(count: number): string {
  return `${(count / 1e9).toFixed(1)}B params`
}

export function formatMs(ms: number | null): string {
  return ms == null ? DASH : `${Math.round(ms)} ms`
}

export function formatSeconds(ms: number | null): string {
  return ms == null ? DASH : `${(ms / 1000).toFixed(1)} s`
}

export function formatTokensPerSec(tokensPerSec: number | null): string {
  return tokensPerSec == null ? DASH : `${tokensPerSec.toFixed(1)} tok/s`
}
