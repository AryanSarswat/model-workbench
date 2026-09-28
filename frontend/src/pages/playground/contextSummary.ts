import type { ContextKind, ContextReport } from '../../api/types'

// Chat-template markup (and llama.cpp's injected tool schemas): prompt tokens that no
// message accounts for.
export type SegmentKind = ContextKind | 'template'

interface ContextSegment {
  kind: SegmentKind
  tokens: number
}

interface ContextSummary {
  segments: ContextSegment[] // empty when the backend couldn't count per message
  used: number | null
  window: number | null
}

// Stacking order of the meter, and of its legend.
const SEGMENT_ORDER: SegmentKind[] = ['system', 'instructions', 'user', 'assistant', 'tool', 'template']

export function summarizeContext(context: ContextReport, promptTokens: number | null): ContextSummary {
  const counted = context.messages.every((message) => message.tokens !== null)
  const totals = new Map<SegmentKind, number>()
  for (const message of context.messages) totals.set(message.kind, (totals.get(message.kind) ?? 0) + (message.tokens ?? 0))
  const messageTokens = [...totals.values()].reduce((sum, tokens) => sum + tokens, 0)
  const used = promptTokens ?? (counted ? messageTokens : null)
  if (!counted) return { segments: [], used, window: context.window }

  // Counts are per message without the template, so they can't exceed an exact prompt
  // count; an estimated one (a GGUF with no chat template) can undershoot them.
  totals.set('template', Math.max((used ?? 0) - messageTokens, 0))
  const segments = SEGMENT_ORDER.flatMap((kind) => {
    const tokens = totals.get(kind) ?? 0
    return tokens > 0 ? [{ kind, tokens }] : []
  })
  return { segments, used, window: context.window }
}
