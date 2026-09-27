import { describe, expect, it } from 'vitest'
import { bestVerdict, formatMemoryRange, gaugeSegments } from './gauge'

const thresholds = { comfortable_fraction: 0.7, tight_fraction: 0.95 }

describe('gaugeSegments', () => {
  it('splits a range across bands and clips at the scale max', () => {
    // usable=20 -> max=30, comfortable<14, tight<19
    const segs = gaugeSegments(10, 40, 20, thresholds)
    expect(segs.map((s) => s.cls)).toEqual(['seg-fit', 'seg-tight', 'hatch'])
    // Clipped to max=30, so the hatch band should end at 100%.
    const hatch = segs.find((s) => s.cls === 'hatch')!
    expect(hatch.left + hatch.width).toBeCloseTo(100, 5)
  })

  // The comfortable/tight boundary comes from the report's comfortable_fraction, so the
  // bands line up with the verdicts the backend computed.
  it('ends the comfortable (fit) band at the report comfortable_fraction of usable memory', () => {
    // usable=20 -> max=30, so 70% of usable (14) sits at 14/30 = 46.666...% of the bar.
    const segs = gaugeSegments(0, 30, 20, thresholds)
    const fit = segs.find((s) => s.cls === 'seg-fit')!
    expect(fit.left).toBe(0)
    expect(fit.left + fit.width).toBeCloseTo((14 / 30) * 100, 5)
  })

  it('keeps a same-value range visible instead of a zero-width sliver', () => {
    const segs = gaugeSegments(8.8, 8.8, 20, thresholds)
    const totalWidth = segs.reduce((sum, s) => sum + s.width, 0)
    expect(totalWidth).toBeGreaterThan(0)
  })
})

describe('bestVerdict', () => {
  it('prefers comfortable over tight over wont_fit', () => {
    expect(bestVerdict(['tight', 'wont_fit', 'comfortable'])).toBe('comfortable')
    expect(bestVerdict(['tight', 'wont_fit'])).toBe('tight')
    expect(bestVerdict(['wont_fit'])).toBe('wont_fit')
    expect(bestVerdict([])).toBeNull()
  })
})

describe('formatMemoryRange', () => {
  it('collapses to a single value when min equals max', () => {
    expect(formatMemoryRange(7.4, 7.4, 1)).toBe('7.4 GB · 1 option')
  })

  it('shows a span and pluralizes the option count', () => {
    expect(formatMemoryRange(8.8, 35.5, 6)).toBe('8.8 – 35.5 GB · 6 options')
  })
})
