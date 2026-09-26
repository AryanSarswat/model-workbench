const DASH = '—'

export function formatMs(ms: number | null): string {
  return ms == null ? DASH : `${Math.round(ms)} ms`
}

export function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

export function formatTokensPerSec(tokensPerSec: number | null): string {
  return tokensPerSec == null ? DASH : `${tokensPerSec.toFixed(1)} tok/s`
}
