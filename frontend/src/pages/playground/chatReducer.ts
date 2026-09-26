import type { BackendName, ChatMessage, TokenUsage, ToolCallRecord } from '../../api/types'

export interface TurnMetrics {
  ttftMs: number | null // request start -> first non-empty delta
  tokensPerSec: number | null // usage.completion_tokens / total seconds
  totalMs: number
}

export interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming: boolean
  stopped: boolean // settled by an aborted Stop, not by done/error
  error: unknown // rendered via <ErrorNotice>; null when the turn has no error
  toolCalls: ToolCallRecord[]
  retries: number
  usage: TokenUsage | null
  metrics: TurnMetrics | null
  hadSchema: boolean // this request carried an output_schema
  modelId: string // the model/backend this turn was actually sent with, for the header
  backend: BackendName // (so switching backend mid-chat doesn't relabel earlier turns)
}

export type ChatAction =
  | { type: 'send'; userId: string; assistantId: string; content: string; hadSchema: boolean; modelId: string; backend: BackendName }
  | { type: 'delta'; id: string; text: string }
  | { type: 'done'; id: string; usage: TokenUsage | null; toolCalls: ToolCallRecord[]; retries: number; metrics: TurnMetrics }
  | { type: 'error'; id: string; error: unknown }
  | { type: 'stop'; id: string }
  | { type: 'reset' }

function newTurn(
  id: string,
  role: ChatTurn['role'],
  content: string,
  streaming: boolean,
  hadSchema: boolean,
  modelId: string,
  backend: BackendName,
): ChatTurn {
  return {
    id,
    role,
    content,
    streaming,
    stopped: false,
    error: null,
    toolCalls: [],
    retries: 0,
    usage: null,
    metrics: null,
    hadSchema,
    modelId,
    backend,
  }
}

// Pure transcript state machine: a user message is appended alongside a streaming
// assistant placeholder, deltas accumulate onto it, and `done`/`error` settle it.
export function chatReducer(state: ChatTurn[], action: ChatAction): ChatTurn[] {
  switch (action.type) {
    case 'send':
      return [
        ...state,
        newTurn(action.userId, 'user', action.content, false, false, action.modelId, action.backend),
        newTurn(action.assistantId, 'assistant', '', true, action.hadSchema, action.modelId, action.backend),
      ]
    case 'delta':
      return state.map((turn) => (turn.id === action.id ? { ...turn, content: turn.content + action.text } : turn))
    case 'done':
      return state.map((turn) =>
        turn.id === action.id
          ? { ...turn, streaming: false, usage: action.usage, toolCalls: action.toolCalls, retries: action.retries, metrics: action.metrics }
          : turn,
      )
    case 'error':
      return state.map((turn) => (turn.id === action.id ? { ...turn, streaming: false, error: action.error } : turn))
    case 'stop':
      return state.map((turn) => (turn.id === action.id ? { ...turn, streaming: false, stopped: true } : turn))
    case 'reset':
      return []
    default:
      return state
  }
}

// Messages to resend as history: a user+assistant pair is dropped when the assistant
// errored or was stopped mid-stream, since resending an empty/partial reply would
// corrupt the next turn's context. `send` always appends a pair together, so turns
// alternate user, assistant, user, assistant, ... in fixed pairs.
export function turnsToHistory(turns: ChatTurn[]): ChatMessage[] {
  const history: ChatMessage[] = []
  for (let i = 0; i < turns.length; i += 2) {
    const user = turns[i]
    const assistant: ChatTurn | undefined = turns[i + 1]
    if (assistant && (assistant.error != null || assistant.stopped)) continue
    history.push({ role: 'user', content: user.content })
    if (assistant) history.push({ role: 'assistant', content: assistant.content })
  }
  return history
}
