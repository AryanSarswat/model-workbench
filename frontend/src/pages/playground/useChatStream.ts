import { useCallback, useReducer, useRef, useState } from 'react'
import { streamChat } from '../../api/endpoints'
import type { BackendName, ChatMessage } from '../../api/types'
import { chatReducer } from './chatReducer'
import { buildChatRequest } from './requestBuilder'

export interface SendMessageOptions {
  modelId: string
  backend: BackendName
  systemPrompt: string
  tools: string[]
  outputSchema: Record<string, unknown> | null
}

let idCounter = 0
function nextId(prefix: string): string {
  idCounter += 1
  return `${prefix}-${idCounter}`
}

// Drives one POST /chat/stream turn into the chatReducer transcript: appends the user
// message and a streaming assistant placeholder, accumulates deltas, and settles the
// turn on the terminal `done`/`error` chunk (or on an aborted Stop).
export function useChatStream() {
  const [turns, dispatch] = useReducer(chatReducer, [])
  const [isStreaming, setIsStreaming] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(
    async (content: string, options: SendMessageOptions) => {
      const trimmed = content.trim()
      if (!trimmed || isStreaming) return

      // The client resends full history every turn; system prompt is added separately.
      const history: ChatMessage[] = turns.map((turn) => ({ role: turn.role, content: turn.content }))
      const userId = nextId('user')
      const assistantId = nextId('assistant')
      const hadSchema = options.outputSchema !== null
      dispatch({ type: 'send', userId, assistantId, content: trimmed, hadSchema })

      const request = buildChatRequest({
        modelId: options.modelId,
        backend: options.backend,
        messages: [...history, { role: 'user', content: trimmed }],
        systemPrompt: options.systemPrompt,
        tools: options.tools,
        outputSchema: options.outputSchema,
      })

      const controller = new AbortController()
      controllerRef.current = controller
      setIsStreaming(true)
      const startedAt = performance.now()
      let firstDeltaAt: number | null = null

      try {
        for await (const chunk of streamChat(request, controller.signal)) {
          if (chunk.delta) {
            firstDeltaAt ??= performance.now()
            dispatch({ type: 'delta', id: assistantId, text: chunk.delta })
          }
          if (chunk.error) {
            dispatch({ type: 'error', id: assistantId, error: new Error(chunk.error) })
            return
          }
          if (chunk.done) {
            const totalMs = performance.now() - startedAt
            const tokensPerSec = chunk.usage && totalMs > 0 ? chunk.usage.completion_tokens / (totalMs / 1000) : null
            dispatch({
              type: 'done',
              id: assistantId,
              usage: chunk.usage,
              toolsCalled: chunk.tools_called,
              retries: chunk.retries,
              metrics: { ttftMs: firstDeltaAt !== null ? firstDeltaAt - startedAt : null, tokensPerSec, totalMs },
            })
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          dispatch({ type: 'stop', id: assistantId })
        } else {
          // Includes a pre-stream ApiError (e.g. a 400 invalid_output_schema) -- shown
          // inline via <ErrorNotice> in the transcript.
          dispatch({ type: 'error', id: assistantId, error: err })
        }
      } finally {
        setIsStreaming(false)
        controllerRef.current = null
      }
    },
    [turns, isStreaming],
  )

  const stop = useCallback(() => controllerRef.current?.abort(), [])

  const newChat = useCallback(() => {
    controllerRef.current?.abort()
    dispatch({ type: 'reset' })
  }, [])

  return { turns, isStreaming, sendMessage, stop, newChat }
}
