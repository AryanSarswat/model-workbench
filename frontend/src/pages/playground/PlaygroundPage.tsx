import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useBackends, useDownloadedModels, useTools } from '../../api/hooks'
import type { BackendName } from '../../api/types'
import { BACKEND_NAMES, STRUCTURED_OUTPUT } from '../../lib/backends'
import { Composer } from './Composer'
import { modelOptionsFor, pickPrefilledModelId } from './modelOptions'
import { ModelBar } from './ModelBar'
import { parseSchemaJson } from './requestBuilder'
import { RequestPanel } from './RequestPanel'
import { Transcript } from './Transcript'
import { useChatStream } from './useChatStream'
import styles from './PlaygroundPage.module.css'

function isBackendName(value: string | null): value is BackendName {
  return value !== null && (BACKEND_NAMES as string[]).includes(value)
}

export default function PlaygroundPage() {
  const [searchParams] = useSearchParams()
  const paramModel = searchParams.get('model')
  const paramBackend = searchParams.get('backend')
  const paramQuant = searchParams.get('quant')
  const initialBackend = isBackendName(paramBackend) ? paramBackend : 'api'

  const [backend, setBackend] = useState<BackendName>(initialBackend)
  const [modelId, setModelId] = useState(paramModel ?? '')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [schemaEnabled, setSchemaEnabled] = useState(false)
  const [schemaText, setSchemaText] = useState('')
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set())
  const [draft, setDraft] = useState('')

  const downloadedQuery = useDownloadedModels()
  const toolsQuery = useTools()
  const backendsQuery = useBackends()

  const records = useMemo(() => downloadedQuery.data ?? [], [downloadedQuery.data])
  const modelOptions = useMemo(() => modelOptionsFor(backend, records), [backend, records])

  // Keep the local-model selection valid: whenever we're on gguf/transformers, the
  // list has loaded, and the current modelId isn't one of its options (first landing
  // on this backend, or the previously selected model vanished/doesn't apply here),
  // pick one -- preferring the URL's ?model=&quant= the first time we land on the
  // backend it named, otherwise just the first option. This runs during render
  // (React's documented pattern for adjusting state to match another value) rather
  // than in an effect. It only sets state when the pick differs from the current
  // modelId, so it converges in at most one extra render: the pick is either a member
  // of modelOptions (the condition then goes false) or, with no options, '' (the pick
  // then equals modelId). Without that guard an empty option list would re-set ''
  // on every render and loop forever.
  // Keying off "not a current option" (rather than a one-shot latch) means switching
  // gguf -> api -> gguf re-picks instead of leaving a stale api model_id selected for
  // gguf, which is exactly the bug this guards against.
  if (backend !== 'api' && !downloadedQuery.isPending && !modelOptions.some((option) => option.modelId === modelId)) {
    const useUrlParams = backend === initialBackend
    const picked = pickPrefilledModelId(modelOptions, useUrlParams ? paramModel : null, useUrlParams ? paramQuant : null)
    if (picked !== modelId) setModelId(picked)
  }

  const schemaParse = schemaEnabled ? parseSchemaJson(schemaText) : null
  const schemaError = schemaParse && !schemaParse.ok ? schemaParse.error : null
  const outputSchema = schemaParse && schemaParse.ok ? schemaParse.schema : null

  const { turns, isStreaming, sendMessage, stop, newChat } = useChatStream()

  const trimmedModelId = modelId.trim()
  const unloadable = modelOptions.find((option) => option.modelId === modelId)?.unloadable ?? null
  const sendDisabled = trimmedModelId === '' || draft.trim() === '' || schemaError !== null || unloadable !== null

  function handleSend() {
    if (sendDisabled || isStreaming) return
    void sendMessage(draft, {
      modelId: trimmedModelId,
      backend,
      systemPrompt,
      tools: Array.from(selectedTools),
      outputSchema,
    })
    setDraft('')
  }

  function toggleTool(name: string) {
    setSelectedTools((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const structuredOutputMode = backendsQuery.data?.[backend].structured_output_mode

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <ModelBar
          backend={backend}
          onBackendChange={setBackend}
          modelId={modelId}
          onModelIdChange={setModelId}
          options={modelOptions}
          unloadable={unloadable}
          recordsLoading={downloadedQuery.isPending}
          recordsError={downloadedQuery.error}
          backends={backendsQuery.data}
          onNewChat={newChat}
        />
        <Transcript turns={turns} />
        <Composer
          value={draft}
          onChange={setDraft}
          onSend={handleSend}
          onStop={stop}
          isStreaming={isStreaming}
          sendDisabled={sendDisabled}
          sendBlockedReason={unloadable?.reason ?? null}
        />
      </main>
      <RequestPanel
        systemPrompt={systemPrompt}
        onSystemPromptChange={setSystemPrompt}
        schemaEnabled={schemaEnabled}
        onSchemaEnabledChange={setSchemaEnabled}
        schemaText={schemaText}
        onSchemaTextChange={setSchemaText}
        schemaError={schemaError}
        explanation={structuredOutputMode && STRUCTURED_OUTPUT[structuredOutputMode].explanation}
        tools={toolsQuery.data ?? []}
        toolsError={toolsQuery.error}
        selectedTools={selectedTools}
        onToggleTool={toggleTool}
      />
    </div>
  )
}
