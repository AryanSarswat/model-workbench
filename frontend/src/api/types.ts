// The backend's request/response types, re-exported under the names the app uses.
// Generated from the backend's OpenAPI schema into schema.gen.ts -- regenerate with
// `make fe-types` after changing a backend model; never edit schema.gen.ts by hand.
// Datetimes arrive as ISO strings. Only what OpenAPI can't express is hand-written
// below: the SSE event payloads, and a few narrowings of the generated types.
import type { components, operations } from './schema.gen'

type Schemas = components['schemas']

// SQLModel types a table's primary key as optional (it's unset until the row is
// inserted); every row the API returns is persisted, so its id is always set.
type Persisted<T> = Omit<T, 'id'> & { id: number }

// --- backends ---

export type BackendInfo = Schemas['BackendInfo'] // GET /backends, keyed by BackendName
export type BackendName = Schemas['EvalRun']['backend']
export type StructuredOutputMode = BackendInfo['structured_output_mode']

// --- config ---

export type GpuInfo = Schemas['GPUInfo']
export type HardwareInfo = Schemas['HardwareInfo']
export type ApiKeyStatus = Schemas['ApiKeyStatus']

// --- discovery ---

export type DiscoverSort = NonNullable<
  NonNullable<operations['discover_models_models_discover_get']['parameters']['query']>['sort']
>
export type DiscoveredModel = Schemas['DiscoveredModel']
export type GgufFile = Schemas['GgufFile']
export type ModelDetail = Schemas['ModelDetail']
export type FeasibilityVerdict = Schemas['FeasibilityOption']['verdict']

// Narrowed from the schema's `filename: string | null`: the backend sets the GGUF file
// to download/load exactly for gguf options, and null for transformers.
export type FeasibilityOption = Omit<Schemas['FeasibilityOption'], 'backend' | 'filename'> &
  ({ backend: 'gguf'; filename: string } | { backend: 'transformers'; filename: null })

export type FeasibilityReport = Omit<Schemas['FeasibilityReport'], 'options'> & {
  options: FeasibilityOption[]
}

// --- downloads ---

// Narrowed from the schema's two optional fields: the backend 400s unless exactly one
// of `filename` / `snapshot: true` is sent.
export type DownloadRequest = { filename: string } | { snapshot: true }

export type DownloadJob = Persisted<Schemas['DownloadJob']>
export type DownloadStatus = DownloadJob['status']
export type DownloadedModelRecord = Schemas['DownloadedModel']

// --- chat ---

export type ChatMessage = Schemas['ChatMessage']
export type ChatRequest = Schemas['ChatRequest']
export type ChatSession = Persisted<Schemas['ChatSession']>
export type ChatMessageRecord = Persisted<Schemas['ChatMessageRecord']>
export type ChatSessionDetail = Omit<Schemas['ChatSessionDetail'], 'messages'> & {
  messages: ChatMessageRecord[]
}

// The chat stream's SSE payloads: FastAPI's schema only covers JSON responses, so
// these mirror app/inference/schemas.py by hand.

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
}

// One executed tool call. `result` is exactly the text the model was sent back
// ("Error: ..." when the tool failed).
export interface ToolCallRecord {
  name: string
  arguments: Record<string, unknown>
  result: string
  duration_ms: number
}

// A tool call that has started running; its ToolCallRecord follows when it ends.
export interface ToolCallStart {
  name: string
  arguments: Record<string, unknown>
}

// Where a message in the model's context came from: the caller's system prompt or
// turns, the workbench's own additions (tool protocol, retry feedback), or a tool result.
export type ContextKind = 'system' | 'instructions' | 'user' | 'assistant' | 'tool'

export interface ContextMessage {
  kind: ContextKind
  content: string
  tokens: number | null // null when the backend has no local tokenizer (the HF API)
}

// Every message the turn's last generation was given. usage.prompt_tokens minus the
// messages' tokens is chat-template markup (and llama.cpp's injected tool schemas).
export interface ContextReport {
  window: number | null // the model's context window; null when unknown (the HF API)
  messages: ContextMessage[]
}

// One SSE event of POST /chat/stream. usage/tools_called/tool_calls/retries/context are
// set on the terminal (done) chunk only. While a tool turn runs, a chunk announces each
// call as it starts and another carries its record as it finishes (calls run one at
// a time, so a finished record closes the latest start).
export interface ChatChunk {
  delta: string
  done: boolean
  error: string | null
  tool_call_started: ToolCallStart | null
  tool_call_finished: ToolCallRecord | null
  usage: TokenUsage | null
  tools_called: string[]
  tool_calls: ToolCallRecord[]
  retries: number
  context?: ContextReport | null // absent from a backend that predates the context report
}

// --- tools ---

export type ToolSpec = Schemas['ToolSpec']

// --- dataset ---

export type Assertion = Schemas['Assertion']
export type AssertionType = Assertion['type']
export type TestCaseJudge = Schemas['TestCaseJudge']
export type TestCase = Schemas['TestCase']

// --- evals ---

export type EvalRunRequest = Schemas['EvalRunRequest']

// One SSE event of POST /evals/run (hand-written for the same reason as ChatChunk;
// built in app/evals/router.py). The final event has done=true, plus error if the run
// failed as a whole.
export interface EvalProgressEvent {
  run_id: number
  completed: number
  total: number
  current_case: string | null
  done: boolean
  error?: string
}

export type EvalRun = Persisted<Schemas['EvalRun']>
export type AssertionResult = Schemas['AssertionResult']
export type EvalResult = Schemas['EvalResultOut']
export type ManualVerdictUpdate = Schemas['ManualVerdictUpdate']
export type ManualVerdict = NonNullable<ManualVerdictUpdate['manual_verdict']>
// One row per (model_id, backend, category), counting only the latest result per case.
export type EvalReportRow = Schemas['EvalReportRow']
