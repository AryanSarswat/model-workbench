import type { TokenUsage } from '../../api/types'

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
  error: unknown // rendered via <ErrorNotice>; null when the turn has no error
  toolsCalled: string[]
  retries: number
  usage: TokenUsage | null
  metrics: TurnMetrics | null
  hadSchema: boolean // this request carried an output_schema
}

export type ChatAction =
  | { type: 'send'; userId: string; assistantId: string; content: string; hadSchema: boolean }
  | { type: 'delta'; id: string; text: string }
  | { type: 'done'; id: string; usage: TokenUsage | null; toolsCalled: string[]; retries: number; metrics: TurnMetrics }
  | { type: 'error'; id: string; error: unknown }
  | { type: 'stop'; id: string }
  | { type: 'reset' }

function newTurn(id: string, role: ChatTurn['role'], content: string, streaming: boolean, hadSchema = false): ChatTurn {
  return { id, role, content, streaming, error: null, toolsCalled: [], retries: 0, usage: null, metrics: null, hadSchema }
}

// Pure transcript state machine: a user message is appended alongside a streaming
// assistant placeholder, deltas accumulate onto it, and `done`/`error` settle it.
export function chatReducer(state: ChatTurn[], action: ChatAction): ChatTurn[] {
  switch (action.type) {
    case 'send':
      return [...state, newTurn(action.userId, 'user', action.content, false), newTurn(action.assistantId, 'assistant', '', true, action.hadSchema)]
    case 'delta':
      return state.map((turn) => (turn.id === action.id ? { ...turn, content: turn.content + action.text } : turn))
    case 'done':
      return state.map((turn) =>
        turn.id === action.id
          ? { ...turn, streaming: false, usage: action.usage, toolsCalled: action.toolsCalled, retries: action.retries, metrics: action.metrics }
          : turn,
      )
    case 'error':
      return state.map((turn) => (turn.id === action.id ? { ...turn, streaming: false, error: action.error } : turn))
    case 'stop':
      return state.map((turn) => (turn.id === action.id ? { ...turn, streaming: false } : turn))
    case 'reset':
      return []
    default:
      return state
  }
}
