import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { listDownloaded, listTools } from '../../api/endpoints'
import type { BackendName } from '../../api/types'
import { BACKEND_NAMES, BACKENDS } from '../../lib/backends'
import { NATIVE_TOOL_CALLING } from './capabilities'
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

  const downloadedQuery = useQuery({ queryKey: ['playground', 'downloaded-models'], queryFn: listDownloaded })
  const toolsQuery = useQuery({ queryKey: ['playground', 'tools'], queryFn: listTools })

  const records = useMemo(() => downloadedQuery.data ?? [], [downloadedQuery.data])
  const modelOptions = useMemo(() => modelOptionsFor(backend, records), [backend, records])

  // Auto-pick a local model once its options are known: prefer the URL's ?model=&quant=
  // the first time we land on the backend it named, otherwise just the first option.
  // Re-runs whenever the backend changes so switching away and back doesn't strand a
  // stale selection.
  const autoPickedFor = useRef<BackendName | null>(null)
  useEffect(() => {
    if (backend === 'api' || downloadedQuery.isPending) return
    if (autoPickedFor.current === backend) return
    autoPickedFor.current = backend
    const useUrlParams = backend === initialBackend
    setModelId(pickPrefilledModelId(modelOptions, useUrlParams ? paramModel : null, useUrlParams ? paramQuant : null))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- paramModel/paramQuant/initialBackend are fixed for the page's lifetime
  }, [backend, downloadedQuery.isPending, modelOptions])

  const schemaParse = schemaEnabled ? parseSchemaJson(schemaText) : null
  const schemaError = schemaParse && !schemaParse.ok ? schemaParse.error : null
  const outputSchema = schemaParse && schemaParse.ok ? schemaParse.schema : null

  const { turns, isStreaming, sendMessage, stop, newChat } = useChatStream()

  const trimmedModelId = modelId.trim()
  const sendDisabled = trimmedModelId === '' || draft.trim() === '' || schemaError !== null

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

  const backendInfo = BACKENDS[backend]
  const nativeTools = NATIVE_TOOL_CALLING[backend]

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <ModelBar
          backend={backend}
          onBackendChange={setBackend}
          modelId={modelId}
          onModelIdChange={setModelId}
          records={records}
          recordsLoading={downloadedQuery.isPending}
          structuredOutputLabel={backendInfo.guarantee}
          structuredOutputTone={backendInfo.guarantee === 'guaranteed' ? 'fit' : 'tight'}
          toolsLabel={nativeTools ? 'native' : 'fallback'}
          toolsTone={nativeTools ? 'fit' : 'tight'}
          onNewChat={newChat}
        />
        <Transcript turns={turns} backend={backend} modelId={modelId} />
        <Composer value={draft} onChange={setDraft} onSend={handleSend} onStop={stop} isStreaming={isStreaming} sendDisabled={sendDisabled} />
      </main>
      <RequestPanel
        systemPrompt={systemPrompt}
        onSystemPromptChange={setSystemPrompt}
        schemaEnabled={schemaEnabled}
        onSchemaEnabledChange={setSchemaEnabled}
        schemaText={schemaText}
        onSchemaTextChange={setSchemaText}
        schemaError={schemaError}
        explanation={backendInfo.explanation}
        tools={toolsQuery.data ?? []}
        toolsError={toolsQuery.error}
        selectedTools={selectedTools}
        onToggleTool={toggleTool}
      />
    </div>
  )
}
