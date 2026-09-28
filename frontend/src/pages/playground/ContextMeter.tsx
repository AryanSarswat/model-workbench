import { useState } from 'react'
import type { ContextReport, TokenUsage } from '../../api/types'
import { summarizeContext, type SegmentKind } from './contextSummary'
import styles from './ContextMeter.module.css'

const LABELS: Record<SegmentKind, string> = {
  system: 'system',
  instructions: 'instructions',
  user: 'user',
  assistant: 'assistant',
  tool: 'tool results',
  template: 'template',
}

// How full the model's context window was on the turn's last generation, what filled
// it, and -- one click away -- the exact messages it was given.
export function ContextMeter({ context, usage }: { context: ContextReport; usage: TokenUsage | null }) {
  const [expanded, setExpanded] = useState(false)
  const { segments, used, window } = summarizeContext(context, usage?.prompt_tokens ?? null)
  const caption = captionFor(used, window)

  return (
    <div className={styles.meter}>
      {window !== null && segments.length > 0 && (
        <div className={styles.bar} role="img" aria-label={`Context: ${caption}`}>
          {segments.map((segment) => (
            <span
              key={segment.kind}
              className={styles.segment}
              data-kind={segment.kind}
              style={{ width: `${(segment.tokens / window) * 100}%` }}
              title={`${LABELS[segment.kind]} · ${segment.tokens.toLocaleString()} tokens`}
            />
          ))}
        </div>
      )}
      <div className={styles.caption}>{caption}</div>
      {segments.length > 0 && (
        <ul className={styles.legend}>
          {segments.map((segment) => (
            <li key={segment.kind}>
              <span className={styles.swatch} data-kind={segment.kind} aria-hidden="true" />
              <span>{LABELS[segment.kind]}</span>
              <span className={styles.count}>{segment.tokens.toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className={styles.toggle} onClick={() => setExpanded(!expanded)}>
        {expanded ? 'Hide context' : 'Show context'}
      </button>
      {expanded && (
        <ol className={styles.messages}>
          {context.messages.map((message, index) => (
            <li key={index} className={styles.message}>
              <div className={styles.messageHead}>
                <span className={styles.swatch} data-kind={message.kind} aria-hidden="true" />
                <span>{LABELS[message.kind]}</span>
                {message.tokens !== null && <span className={styles.count}>{message.tokens.toLocaleString()} tokens</span>}
              </div>
              <pre className={styles.content}>{message.content}</pre>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function captionFor(used: number | null, window: number | null): string {
  if (used === null) return '— prompt tokens'
  if (window === null) return `${used.toLocaleString()} prompt tokens · window unknown`
  return `${used.toLocaleString()} / ${window.toLocaleString()} tokens · ${Math.round((used / window) * 100)}%`
}
