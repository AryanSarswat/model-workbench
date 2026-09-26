import { Link } from 'react-router'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Eyebrow } from '../../components/Eyebrow'
import { Field } from '../../components/Field'
import type { ToolSpec } from '../../api/types'
import styles from './RequestPanel.module.css'

export function RequestPanel({
  systemPrompt,
  onSystemPromptChange,
  schemaEnabled,
  onSchemaEnabledChange,
  schemaText,
  onSchemaTextChange,
  schemaError,
  explanation,
  tools,
  toolsError,
  selectedTools,
  onToggleTool,
}: {
  systemPrompt: string
  onSystemPromptChange: (value: string) => void
  schemaEnabled: boolean
  onSchemaEnabledChange: (enabled: boolean) => void
  schemaText: string
  onSchemaTextChange: (value: string) => void
  schemaError: string | null
  explanation: string
  tools: ToolSpec[]
  toolsError: unknown
  selectedTools: Set<string>
  onToggleTool: (name: string) => void
}) {
  return (
    <aside aria-label="Request settings" className={styles.aside}>
      <section className={styles.section}>
        <Field label="System prompt" htmlFor="playground-system-prompt">
          <textarea
            id="playground-system-prompt"
            rows={3}
            className={styles.systemTextarea}
            value={systemPrompt}
            onChange={(event) => onSystemPromptChange(event.target.value)}
          />
        </Field>
      </section>

      <section className={styles.section}>
        <Eyebrow as="h2">Structured output</Eyebrow>
        <label className={styles.checkboxLabel}>
          <input type="checkbox" checked={schemaEnabled} onChange={(event) => onSchemaEnabledChange(event.target.checked)} />
          Constrain replies to a JSON Schema
        </label>
        {schemaEnabled && (
          <>
            <textarea
              aria-label="JSON Schema"
              rows={8}
              className={styles.schemaTextarea}
              value={schemaText}
              onChange={(event) => onSchemaTextChange(event.target.value)}
            />
            {schemaError && <p className={styles.schemaError}>{schemaError}</p>}
          </>
        )}
        <p className={styles.explanation}>{explanation}</p>
      </section>

      <section className={styles.section}>
        <div className={styles.toolsHeader}>
          <Eyebrow as="h2">Tools</Eyebrow>
          <Link to="/library" className={styles.manageLink}>
            Manage
          </Link>
        </div>
        {toolsError ? (
          <ErrorNotice error={toolsError} />
        ) : tools.length === 0 ? (
          <p className={styles.empty}>No tools available.</p>
        ) : (
          tools.map((tool) => (
            <label key={tool.name} className={styles.toolRow}>
              <input type="checkbox" checked={selectedTools.has(tool.name)} onChange={() => onToggleTool(tool.name)} />
              <span className={styles.toolInfo}>
                <span className={styles.toolName}>{tool.name}</span>
                <span className={styles.toolDescription}>{tool.description}</span>
              </span>
            </label>
          ))
        )}
      </section>
    </aside>
  )
}
