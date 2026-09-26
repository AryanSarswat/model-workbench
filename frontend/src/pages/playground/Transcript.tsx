import { useState } from 'react'
import type { ToolCallRecord, ToolCallStart } from '../../api/types'
import { Chip, type ChipTone } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { LiveDot } from '../../components/LiveDot'
import { NATIVE_TOOL_CALLING } from './capabilities'
import type { ChatTurn } from './chatReducer'
import { formatMs, formatSeconds, formatTokensPerSec } from './format'
import { backendDisplayLabel, shortModelName } from './modelOptions'
import { parseSchemaJson } from './requestBuilder'
import styles from './Transcript.module.css'

export function Transcript({ turns }: { turns: ChatTurn[] }) {
  return (
    <div className={styles.transcript}>
      {turns.map((turn) =>
        turn.role === 'user' ? (
          <article key={turn.id} className={styles.userTurn}>
            <div className="eyebrow">You</div>
            <p className={styles.userText}>{turn.content}</p>
          </article>
        ) : (
          <AssistantTurn key={turn.id} turn={turn} />
        ),
      )}
    </div>
  )
}

// Each turn renders with the model/backend it was actually sent with (stored on the
// turn by useChatStream), not the page's current selection -- otherwise switching
// models mid-chat would relabel earlier turns.
function AssistantTurn({ turn }: { turn: ChatTurn }) {
  const toolsNative = NATIVE_TOOL_CALLING[turn.backend]
  const toolsChipLabel = toolsNative ? 'native' : 'fallback'
  const toolsChipTone = toolsNative ? 'fit' : 'tight'
  const showToolBlocks = turn.toolCalls.length > 0 || turn.runningTool !== null
  const settled = !turn.streaming && !turn.error

  let schemaBlock: { valid: boolean; body: string } | null = null
  if (turn.hadSchema && settled) {
    const parsed = parseSchemaJson(turn.content)
    schemaBlock = parsed.ok ? { valid: true, body: JSON.stringify(parsed.schema, null, 2) } : { valid: false, body: turn.content }
  }

  return (
    <article className={styles.assistantTurn}>
      <div className={styles.header}>
        <div className="eyebrow">
          {shortModelName(turn.modelId)} · {backendDisplayLabel(turn.backend, turn.modelId)}
        </div>
        {turn.streaming && <LiveDot>{turn.runningTool ? 'running tool' : 'streaming'}</LiveDot>}
      </div>

      {showToolBlocks && (
        <>
          {turn.toolCalls.map((call, index) => (
            <ToolCallCard key={index} call={call} modeLabel={toolsChipLabel} modeTone={toolsChipTone} />
          ))}
          {turn.runningTool && <RunningToolCard call={turn.runningTool} modeLabel={toolsChipLabel} modeTone={toolsChipTone} />}
          {turn.retries > 0 && <p className={styles.retriesNote}>retried {turn.retries}×</p>}
        </>
      )}

      {schemaBlock && (
        <div className={styles.block}>
          <div className={styles.blockHeader}>
            <span className={styles.blockTitle}>structured output</span>
            <Chip tone={schemaBlock.valid ? 'fit' : 'nofit'}>
              {schemaBlock.valid ? `schema valid · ${retryLabel(turn.retries)}` : 'invalid JSON'}
            </Chip>
          </div>
          <pre className={styles.code}>{schemaBlock.body}</pre>
        </div>
      )}

      {!turn.hadSchema && (
        <p className={styles.reply}>
          {turn.content}
          {turn.streaming && <span className={styles.caret} aria-hidden="true" />}
        </p>
      )}

      {/* Announced once, when the turn settles -- not per token, unlike the paragraph above. */}
      {settled && !turn.hadSchema && (
        <p className={styles.srOnly} aria-live="polite">
          {turn.content ? `Reply ready: ${turn.content}` : 'Reply ready.'}
        </p>
      )}

      {settled && (
        <div className={styles.metrics}>
          <span>TTFT {formatMs(turn.metrics?.ttftMs ?? null)}</span>
          <span>{formatTokensPerSec(turn.metrics?.tokensPerSec ?? null)}</span>
          <span>{turn.usage ? `${turn.usage.completion_tokens} tokens` : '— tokens'}</span>
          <span>{turn.metrics ? formatSeconds(turn.metrics.totalMs) : '—'}</span>
        </div>
      )}

      {turn.error != null && <ErrorNotice error={turn.error} />}
    </article>
  )
}

// Longer results start collapsed to a preview; the full text is one click away.
const PREVIEW_CHARS = 280

function ToolCallCard({ call, modeLabel, modeTone }: { call: ToolCallRecord; modeLabel: string; modeTone: ChipTone }) {
  const [expanded, setExpanded] = useState(false)
  // Tools report failure as an "Error: ..." result rather than raising (see backend app/tools).
  const failed = call.result.startsWith('Error:')
  const collapsible = call.result.length > PREVIEW_CHARS
  const shown = collapsible && !expanded ? `${call.result.slice(0, PREVIEW_CHARS)}…` : call.result

  return (
    <div className={[styles.block, failed && styles.blockFailed].filter(Boolean).join(' ')}>
      <div className={styles.blockHeader}>
        <span className={styles.blockTitle}>tool call · {call.name}</span>
        <span className={styles.chips}>
          <Chip tone={modeTone}>{modeLabel}</Chip>
          <Chip tone={failed ? 'nofit' : 'fit'}>{failed ? 'error' : `ok · ${call.result.length.toLocaleString()} chars`}</Chip>
        </span>
      </div>
      <ToolArgs args={call.arguments} />
      <div className={styles.result}>
        <div className={styles.resultMeta}>
          <span>result · sent to model</span>
          <span>{formatMs(call.duration_ms)}</span>
        </div>
        <pre className={[styles.code, failed && styles.errorText].filter(Boolean).join(' ')}>{shown}</pre>
        {failed && <p className={styles.resultNote}>The model received this error as the tool's result.</p>}
        {collapsible && (
          <button type="button" className={styles.toggle} onClick={() => setExpanded(!expanded)}>
            {expanded ? 'Show less' : 'Show full result'}
          </button>
        )}
      </div>
    </div>
  )
}

// The call executing right now: what it was asked, with no result yet.
function RunningToolCard({ call, modeLabel, modeTone }: { call: ToolCallStart; modeLabel: string; modeTone: ChipTone }) {
  return (
    <div className={[styles.block, styles.blockRunning].join(' ')}>
      <div className={styles.blockHeader}>
        <span className={styles.blockTitle}>tool call · {call.name}</span>
        <span className={styles.chips}>
          <Chip tone={modeTone}>{modeLabel}</Chip>
          <Chip tone="idle">{call.name === 'web_fetch' ? 'fetching…' : 'running…'}</Chip>
        </span>
      </div>
      <ToolArgs args={call.arguments} />
    </div>
  )
}

function ToolArgs({ args }: { args: Record<string, unknown> }) {
  if (Object.keys(args).length === 0) return null
  return (
    <dl className={styles.args}>
      {Object.entries(args).map(([key, value]) => (
        <div key={key} className={styles.arg}>
          <dt>{key}</dt>
          <dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

function retryLabel(retries: number): string {
  return retries === 0 ? 'first try' : `after ${retries} retr${retries === 1 ? 'y' : 'ies'}`
}
