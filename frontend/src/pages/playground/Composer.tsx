import type { KeyboardEvent } from 'react'
import { Button } from '../../components/Button'
import { Field } from '../../components/Field'
import styles from './Composer.module.css'

export function Composer({
  value,
  onChange,
  onSend,
  onStop,
  isStreaming,
  sendDisabled,
  sendBlockedReason,
}: {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  isStreaming: boolean
  sendDisabled: boolean
  sendBlockedReason: string | null // shown beside Send, e.g. why the model can't load
}) {
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter inserts a newline; only Cmd/Ctrl+Enter (or the button) sends.
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault()
      if (!sendDisabled) onSend()
    }
  }

  return (
    <div className={styles.composer}>
      <Field label="Message" htmlFor="playground-message" className={styles.field}>
        <textarea
          id="playground-message"
          rows={2}
          className={styles.textarea}
          placeholder="Ask something, or paste a prompt from your dataset"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
        />
      </Field>
      {sendBlockedReason && (
        <p id="composer-blocked-reason" className={styles.blockedReason}>
          {sendBlockedReason}
        </p>
      )}
      <Button
        variant="outline"
        className={[styles.action, isStreaming && styles.stop].filter(Boolean).join(' ')}
        onClick={isStreaming ? onStop : onSend}
        disabled={!isStreaming && sendDisabled}
        aria-describedby={sendBlockedReason ? 'composer-blocked-reason' : undefined}
      >
        {isStreaming ? (
          <>
            <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
              <rect x="3" y="3" width="10" height="10" fill="currentColor" />
            </svg>
            Stop
          </>
        ) : (
          'Send'
        )}
      </Button>
    </div>
  )
}
