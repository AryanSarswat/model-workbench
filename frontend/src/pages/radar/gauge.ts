// Memory-fit gauge math, shared by the Radar table and the Model detail page.
// Mirrors the backend's verdict thresholds (backend/app/discovery/feasibility.py
// _COMFORTABLE_THRESHOLD / _TIGHT_THRESHOLD) so the bar's bands line up with the verdicts
// the API already computed.
import { getFeasibility } from '../../api/endpoints'
import type { FeasibilityVerdict } from '../../api/types'
import type { ChipTone } from '../../components/Chip'

const COMFORTABLE_THRESHOLD = 0.7
const TIGHT_THRESHOLD = 0.95

// The scale runs to 1.5x usable memory, so the capacity line (== usable memory) sits at
// exactly 2/3 (66.67%) of the bar.
const SCALE_FACTOR = 1.5

// Keeps a same-value (lo === hi) range visible as a sliver rather than a zero-width bar.
// Proportional to the scale so it looks the same regardless of how much memory is usable.
const MIN_SEGMENT_FRACTION = 0.6 / 27

export type SegmentClass = 'seg-fit' | 'seg-tight' | 'hatch'

export interface GaugeSegment {
  cls: SegmentClass
  left: number // percent of the scale
  width: number // percent of the scale
}

export interface GaugeScale {
  max: number
  comfortableGb: number
  tightGb: number
}

export function gaugeScale(usableMemoryGb: number): GaugeScale {
  return {
    max: usableMemoryGb * SCALE_FACTOR,
    comfortableGb: usableMemoryGb * COMFORTABLE_THRESHOLD,
    tightGb: usableMemoryGb * TIGHT_THRESHOLD,
  }
}

// Colored segments for the part of [lo, hi] inside each band, clipped to the scale's max.
export function gaugeSegments(lo: number, hi: number, usableMemoryGb: number): GaugeSegment[] {
  const { max, comfortableGb, tightGb } = gaugeScale(usableMemoryGb)
  const minWidth = max * MIN_SEGMENT_FRACTION
  const bands: [number, number, SegmentClass][] = [
    [0, comfortableGb, 'seg-fit'],
    [comfortableGb, tightGb, 'seg-tight'],
    [tightGb, max, 'hatch'],
  ]
  const a = Math.min(lo, max - minWidth)
  const b = Math.max(Math.min(hi, max), a + minWidth)
  return bands
    .map(([start, end, cls]) => ({ start: Math.max(a, start), end: Math.min(b, end), cls }))
    .filter((seg) => seg.end > seg.start)
    .map((seg) => ({
      cls: seg.cls,
      left: (seg.start / max) * 100,
      width: ((seg.end - seg.start) / max) * 100,
    }))
}

export const VERDICT_LABEL: Record<FeasibilityVerdict, string> = {
  comfortable: 'Fits',
  tight: 'Tight',
  wont_fit: 'Won’t fit',
}

export const VERDICT_CHIP_TONE: Record<FeasibilityVerdict, ChipTone> = {
  comfortable: 'fit',
  tight: 'tight',
  wont_fit: 'nofit',
}

// Best (most favorable) verdict among a repo's options, comfortable > tight > wont_fit.
const VERDICT_RANK: Record<FeasibilityVerdict, number> = { comfortable: 0, tight: 1, wont_fit: 2 }

export function bestVerdict(verdicts: FeasibilityVerdict[]): FeasibilityVerdict | null {
  if (verdicts.length === 0) return null
  return verdicts.reduce((best, v) => (VERDICT_RANK[v] < VERDICT_RANK[best] ? v : best))
}

export function formatGbValue(gb: number): string {
  return gb.toFixed(1)
}

// "8.8 – 35.5 GB · 6 options" (single value when min === max).
export function formatMemoryRange(lo: number, hi: number, optionCount: number): string {
  const span = lo === hi ? `${formatGbValue(lo)} GB` : `${formatGbValue(lo)} – ${formatGbValue(hi)} GB`
  return `${span} · ${optionCount} option${optionCount === 1 ? '' : 's'}`
}

const FEASIBILITY_STALE_TIME = 10 * 60 * 1000

// Shared query options for a model's feasibility report -- used both by the Radar table
// (one per row, via useQueries) and the Model detail page (one, via useQuery), so the two
// pages hit the same cache entry with the same staleTime/retry instead of racing configs.
export function feasibilityQueryOptions(modelId: string) {
  return {
    queryKey: ['models', modelId, 'feasibility'] as const,
    queryFn: () => getFeasibility(modelId),
    staleTime: FEASIBILITY_STALE_TIME,
    retry: false,
  }
}
