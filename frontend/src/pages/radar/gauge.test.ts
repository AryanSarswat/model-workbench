import { describe, expect, it } from 'vitest'
import { bestVerdict, formatMemoryRange, gaugeSegments, verdictFor } from './gauge'

describe('verdictFor', () => {
  // Mirrors backend/app/discovery/feasibility.py's _COMFORTABLE_THRESHOLD/_TIGHT_THRESHOLD
  // (0.7 / 0.95 of usable memory) -- these bands are what the whole gauge is built on.
  it('bands against usable memory the same way the backend does', () => {
    expect(verdictFor(10, 20)).toBe('comfortable') // < 70% of 20
    expect(verdictFor(15, 20)).toBe('tight') // between 70% and 95%
    expect(verdictFor(19, 20)).toBe('wont_fit') // >= 95%
  })
})

describe('gaugeSegments', () => {
  it('splits a range across bands and clips at the scale max', () => {
    // usable=20 -> max=30, comfortable<14, tight<19
    const segs = gaugeSegments(10, 40, 20)
    expect(segs.map((s) => s.cls)).toEqual(['seg-fit', 'seg-tight', 'hatch'])
    // Clipped to max=30, so the hatch band should end at 100%.
    const hatch = segs.find((s) => s.cls === 'hatch')!
    expect(hatch.left + hatch.width).toBeCloseTo(100, 5)
  })

  it('keeps a same-value range visible instead of a zero-width sliver', () => {
    const segs = gaugeSegments(8.8, 8.8, 20)
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
