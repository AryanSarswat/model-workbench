// Mirrors of the backend's request/response models. Datetimes arrive as ISO strings;
// optional backend fields are serialized as null, never omitted.

export type BackendName = 'api' | 'gguf' | 'transformers'

// --- config ---

export interface GpuInfo {
  kind: 'apple_silicon' | 'nvidia' | 'none'
  name: string | null
  vram_gb: number | null
}

export interface HardwareInfo {
  platform: string
  arch: string
  total_ram_gb: number
  gpu: GpuInfo
  usable_memory_gb: number // computed server-side: NVIDIA VRAM if known, else total RAM
}

export interface ApiKeyStatus {
  is_set: boolean
}

// --- discovery ---

export type DiscoverSort = 'trending' | 'recent'

export interface DiscoveredModel {
  id: string
  author: string | null
  pipeline_tag: string | null
  downloads: number | null
  likes: number | null
  trending_score: number | null
  created_at: string | null
  gated: boolean | string | null // false, or a reason like "auto"/"manual"
  tags: string[]
  library_name: string | null
}

export interface GgufFile {
  filename: string
  size_bytes: number
}

export interface ModelDetail extends DiscoveredModel {
  gguf_files: GgufFile[]
  parameter_count: number | null
  dtype: string | null
}

export type FeasibilityVerdict = 'comfortable' | 'tight' | 'wont_fit'

export interface FeasibilityOption {
  label: string // a GGUF filename, or e.g. "transformers (BF16)"
  verdict: FeasibilityVerdict
  estimated_memory_gb: number
  reason: string
}

export interface FeasibilityReport {
  available_memory_gb: number
  options: FeasibilityOption[]
}

// --- downloads ---

export type DownloadRequest = { filename: string } | { snapshot: true }

export type DownloadStatus = 'pending' | 'downloading' | 'completed' | 'failed'

export interface DownloadJob {
  id: number
  repo_id: string
  kind: 'gguf' | 'snapshot'
  filename: string | null // the requested GGUF file; null for snapshots
  current_file: string | null // snapshots only
  status: DownloadStatus
  percent: number // 0..100
  detail: string
  error: string | null
  downloaded_model_id: number | null
  created_at: string
  updated_at: string
}

export interface DownloadedModelRecord {
  id: number
  repo_id: string
  backend: 'gguf' | 'transformers'
  quant: string | null // GGUF filename when backend is gguf
  local_path: string
  size_bytes: number
  downloaded_at: string
  last_used_at: string | null
}

// --- chat ---

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  model_id: string
  messages: ChatMessage[]
  backend?: BackendName // server default: 'api'
  tools?: string[] | null // tool names
  output_schema?: Record<string, unknown> | null // raw JSON Schema
  session_id?: number | null // file this turn into an existing session
}

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

// One SSE event of POST /chat/stream. usage/tools_called/tool_calls/retries are set
// on the terminal (done) chunk only.
export interface ChatChunk {
  delta: string
  done: boolean
  error: string | null
  usage: TokenUsage | null
  tools_called: string[]
  tool_calls: ToolCallRecord[]
  retries: number
}

export interface ChatSession {
  id: number
  created_at: string
}

export interface ChatMessageRecord {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  sequence: number
  created_at: string
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessageRecord[]
}

// --- tools ---

export interface ToolSpec {
  name: string
  description: string
  parameters: Record<string, unknown> // JSON Schema of the arguments
}

// --- dataset ---

export type AssertionType =
  | 'schema_valid'
  | 'contains'
  | 'regex'
  | 'tool_called'
  | 'structured_output_first_try'
  | 'native_tool_calling'
  | 'json_parse_success'

export interface Assertion {
  type: AssertionType
  value?: string | null // contains
  pattern?: string | null // regex
  name?: string | null // tool_called
}

export interface TestCaseJudge {
  criteria: string
}

// Responses always carry every field; only id/category/messages are required on write.
export interface TestCase {
  id: string // URL-safe: letters, digits, . _ -
  category: string
  messages: ChatMessage[]
  system_prompt?: string | null
  output_schema?: Record<string, unknown> | null
  expected_tools?: string[] | null
  assertions?: Assertion[]
  judge?: TestCaseJudge | null
  tags?: string[]
}

// --- evals ---

export interface EvalRunRequest {
  model_id: string
  backend?: BackendName // server default: 'api'
  category?: string | null // null runs every category
  judge_model_id?: string | null
}

// One SSE event of POST /evals/run. The final event has done=true, plus error if the
// run failed as a whole.
export interface EvalProgressEvent {
  completed: number
  total: number
  current_case: string | null
  done: boolean
  error?: string
}

export interface EvalRun {
  id: number
  model_id: string
  backend: BackendName
  category: string | null
  judge_model_id: string | null
  status: 'running' | 'completed' | 'failed'
  total_cases: number
  completed_cases: number
  created_at: string
  finished_at: string | null
}

export interface AssertionResult {
  type: AssertionType
  passed: boolean
  detail: string
}

export type ManualVerdict = 'pass' | 'fail'

export interface EvalResult {
  id: number
  run_id: number
  case_id: string
  category: string
  response: string
  error: string | null
  structured_output_mode: 'grammar' | 'guided' | 'prompt_retry' | null
  native_tool_calling: boolean
  retries: number
  tools_called: string // comma-joined tool names
  assertions_passed: number
  assertions_total: number
  assertions_detail: string // JSON-encoded AssertionResult[]
  judge_score: number | null // 0..1
  judge_rationale: string | null
  manual_verdict: ManualVerdict | null
  manual_notes: string | null
  response_metric_id: number | null
  created_at: string
}

export interface ManualVerdictUpdate {
  manual_verdict: ManualVerdict | null
  manual_notes: string | null
}

// One row per (model_id, backend, category), counting only the latest result per case.
export interface EvalReportRow {
  model_id: string
  backend: BackendName
  category: string
  cases: number
  passed: number
  pass_rate: number // 0..1
  avg_tokens_per_sec: number | null
  avg_ttft_ms: number | null
  structured_output_reliability: number | null
  tool_calling_reliability: number | null
  latest_run_id: number
}
