import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { LiveDot } from '../../components/LiveDot'
import type { BackendName } from '../../api/types'
import { NATIVE_TOOL_CALLING } from './capabilities'
import type { ChatTurn } from './chatReducer'
import { formatMs, formatSeconds, formatTokensPerSec } from './format'
import { backendDisplayLabel, shortModelName } from './modelOptions'
import { parseSchemaJson } from './requestBuilder'
import styles from './Transcript.module.css'

export function Transcript({ turns, backend, modelId }: { turns: ChatTurn[]; backend: BackendName; modelId: string }) {
  return (
    <div className={styles.transcript}>
      {turns.map((turn) =>
        turn.role === 'user' ? (
          <article key={turn.id} className={styles.userTurn}>
            <div className="eyebrow">You</div>
            <p className={styles.userText}>{turn.content}</p>
          </article>
        ) : (
          <AssistantTurn key={turn.id} turn={turn} backend={backend} modelId={modelId} />
        ),
      )}
    </div>
  )
}

function AssistantTurn({ turn, backend, modelId }: { turn: ChatTurn; backend: BackendName; modelId: string }) {
  const toolsNative = NATIVE_TOOL_CALLING[backend]
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
          {shortModelName(modelId)} · {backendDisplayLabel(backend, modelId)}
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
        <p className={styles.reply} aria-live="polite">
          {turn.content}
          {turn.streaming && <span className={styles.caret} aria-hidden="true" />}
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
