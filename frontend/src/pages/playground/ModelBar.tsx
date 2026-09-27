import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Button } from '../../components/Button'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Field } from '../../components/Field'
import { SegmentedControl } from '../../components/SegmentedControl'
import { BACKEND_NAMES, BACKENDS, structuredOutputChip, toolCallingChip } from '../../lib/backends'
import type { BackendInfo, BackendName } from '../../api/types'
import type { ModelOption } from './modelOptions'
import styles from './ModelBar.module.css'

export function ModelBar({
  backend,
  onBackendChange,
  modelId,
  onModelIdChange,
  options,
  unloadable,
  recordsLoading,
  recordsError,
  backends,
  onNewChat,
}: {
  backend: BackendName
  onBackendChange: (backend: BackendName) => void
  modelId: string
  onModelIdChange: (modelId: string) => void
  options: ModelOption[]
  unloadable: ModelOption['unloadable']
  recordsLoading: boolean
  recordsError: unknown
  backends: Record<BackendName, BackendInfo> | undefined // undefined while GET /backends loads
  onNewChat: () => void
}) {
  const capabilities = backends?.[backend]
  const jsonChip = structuredOutputChip(capabilities?.structured_output_mode)
  const toolsChip = toolCallingChip(capabilities?.native_tool_calling)

  return (
    <div className={styles.bar}>
      {backend === 'api' ? (
        <Field label="Model" htmlFor="playground-model">
          <input
            id="playground-model"
            className={`field ${styles.control}`}
            placeholder="org/model-name"
            value={modelId}
            onChange={(event) => onModelIdChange(event.target.value)}
          />
        </Field>
      ) : recordsError ? (
        <div className={styles.backendField}>
          <span className="eyebrow">Model</span>
          <ErrorNotice error={recordsError} />
        </div>
      ) : recordsLoading ? (
        <ModelHint>Loading downloaded models…</ModelHint>
      ) : options.length === 0 ? (
        <ModelHint>
          No {BACKENDS[backend].label.toLowerCase()} models downloaded. <Link to="/">Browse Radar</Link> to download one.
        </ModelHint>
      ) : (
        <Field label="Model" htmlFor="playground-model">
          <select
            id="playground-model"
            className={[`field ${styles.control}`, unloadable && styles.unloadable].filter(Boolean).join(' ')}
            aria-invalid={unloadable !== null}
            value={modelId}
            onChange={(event) => onModelIdChange(event.target.value)}
          >
            {options.map((option) => (
              <option key={option.modelId} value={option.modelId}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
      )}

      <div className={styles.backendField}>
        <span id="playground-backend-label" className="eyebrow">
          Backend
        </span>
        <SegmentedControl
          labelledBy="playground-backend-label"
          mono
          value={backend}
          onChange={onBackendChange}
          options={BACKEND_NAMES.map((name) => ({ value: name, label: BACKENDS[name].label }))}
        />
      </div>

      <div className={styles.chips}>
        {unloadable ? (
          <Chip tone="nofit">quant {unloadable.quant} · not loadable</Chip>
        ) : (
          <>
            <Chip tone={jsonChip.tone}>JSON · {jsonChip.label}</Chip>
            <Chip tone={toolsChip.tone}>tools · {toolsChip.label}</Chip>
          </>
        )}
        <Button variant="outline" onClick={onNewChat}>
          New chat
        </Button>
      </div>
    </div>
  )
}

function ModelHint({ children }: { children: ReactNode }) {
  return (
    <div className={styles.backendField}>
      <span className="eyebrow">Model</span>
      <p className={styles.hint}>{children}</p>
    </div>
  )
}
