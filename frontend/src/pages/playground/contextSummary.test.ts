import { describe, expect, it } from 'vitest'
import type { ContextReport } from '../../api/types'
import { summarizeContext } from './contextSummary'

const report: ContextReport = {
  window: 1000,
  messages: [
    { kind: 'instructions', content: 'protocol', tokens: 90 },
    { kind: 'user', content: 'q', tokens: 10 },
    { kind: 'assistant', content: 'call', tokens: 20 },
    { kind: 'tool', content: 'result 1', tokens: 150 },
    { kind: 'assistant', content: 'call', tokens: 20 },
    { kind: 'tool', content: 'result 2', tokens: 50 },
  ],
}

describe('summarizeContext', () => {
  it('totals each kind in a fixed order, with template markup as the remainder', () => {
    // The meter answers "what is filling the window": repeated tool results add up
    // under one segment, and whatever the messages don't account for is template.
    const summary = summarizeContext(report, 400)

    expect(summary.segments).toEqual([
      { kind: 'instructions', tokens: 90 },
      { kind: 'user', tokens: 10 },
      { kind: 'assistant', tokens: 40 },
      { kind: 'tool', tokens: 200 },
      { kind: 'template', tokens: 60 },
    ])
    expect(summary.used).toBe(400)
    expect(summary.window).toBe(1000)
  })

  it('has no breakdown when the backend could not count tokens', () => {
    // The HF API: the provider's prompt_tokens is the only figure, and attributing
    // all of it to "template" would be a lie.
    const remote: ContextReport = { window: null, messages: [{ kind: 'user', content: 'hi', tokens: null }] }

    const summary = summarizeContext(remote, 12)

    expect(summary.segments).toEqual([])
    expect(summary.used).toBe(12)
    expect(summary.window).toBeNull()
  })
})
