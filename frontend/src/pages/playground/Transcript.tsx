import { Chip } from '../../components/Chip'
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
  const showToolBlocks = turn.toolsCalled.length > 0
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
        {turn.streaming && <LiveDot>streaming</LiveDot>}
      </div>

      {showToolBlocks && (
        <>
          {turn.toolsCalled.map((name, index) => (
            <div key={`${name}-${index}`} className={styles.block}>
              <div className={styles.blockHeader}>
                <span className={styles.blockTitle}>tool call · {name}</span>
                <Chip tone={toolsChipTone}>{toolsChipLabel}</Chip>
              </div>
            </div>
          ))}
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

function retryLabel(retries: number): string {
  return retries === 0 ? 'first try' : `after ${retries} retr${retries === 1 ? 'y' : 'ies'}`
}
