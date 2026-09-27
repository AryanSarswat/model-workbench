// One typed function per backend endpoint.
import { apiGet, apiSend } from './client'
import { postSse } from './sse'
import type {
  ApiKeyStatus,
  BackendInfo,
  BackendName,
  ChatChunk,
  ChatRequest,
  DiscoverSort,
  DiscoveredModel,
  DownloadJob,
  DownloadRequest,
  DownloadedModelRecord,
  EvalProgressEvent,
  EvalReportRow,
  EvalResult,
  EvalRun,
  EvalRunRequest,
  FeasibilityReport,
  HardwareInfo,
  ManualVerdictUpdate,
  ModelDetail,
  TestCase,
  ToolSpec,
} from './types'

// Model ids contain a slash ("Qwen/Qwen3-14B") that the backend's {model_id:path}
// routes expect literally: encode each segment, keep the "/".
export function modelPath(modelId: string): string {
  return modelId.split('/').map(encodeURIComponent).join('/')
}

// --- discovery & downloads ---

export const discoverModels = (sort: DiscoverSort, limit?: number) =>
  apiGet<DiscoveredModel[]>(`/models/discover?${new URLSearchParams({ sort, ...(limit ? { limit: String(limit) } : {}) })}`)

export const getModel = (modelId: string) => apiGet<ModelDetail>(`/models/${modelPath(modelId)}`)

export const getFeasibility = (modelId: string, quant?: string) =>
  apiGet<FeasibilityReport>(
    `/models/${modelPath(modelId)}/feasibility${quant ? `?${new URLSearchParams({ quant })}` : ''}`,
  )

export const startDownload = (modelId: string, request: DownloadRequest) =>
  apiSend<DownloadJob>('POST', `/models/${modelPath(modelId)}/download`, request)

export const listDownloaded = () => apiGet<DownloadedModelRecord[]>('/models/downloaded')

export const deleteDownloaded = (recordId: number) =>
  apiSend<void>('DELETE', `/models/downloaded/${recordId}`)

// --- chat ---

export const streamChat = (request: ChatRequest, signal?: AbortSignal) =>
  postSse<ChatChunk>('/chat/stream', request, signal)

// --- config ---

export const getHardware = () => apiGet<HardwareInfo>('/config/hardware')

export const getHfKeyStatus = () => apiGet<ApiKeyStatus>('/config/hf-api-key')

export const setHfKey = (apiKey: string) =>
  apiSend<ApiKeyStatus>('POST', '/config/hf-api-key', { api_key: apiKey })

// --- tools ---

export const listTools = () => apiGet<ToolSpec[]>('/tools')

export const getBackends = () => apiGet<Record<BackendName, BackendInfo>>('/backends')

export const reloadTools = () => apiSend<{ count: number }>('POST', '/tools/reload')

// --- dataset ---

export const listCases = (category?: string) =>
  apiGet<TestCase[]>(`/dataset/cases${category ? `?${new URLSearchParams({ category })}` : ''}`)

export const getCase = (caseId: string) =>
  apiGet<TestCase>(`/dataset/cases/${encodeURIComponent(caseId)}`)

export const createCase = (testCase: TestCase) => apiSend<TestCase>('POST', '/dataset/cases', testCase)

export const updateCase = (testCase: TestCase) =>
  apiSend<TestCase>('PUT', `/dataset/cases/${encodeURIComponent(testCase.id)}`, testCase)

export const deleteCase = (caseId: string) =>
  apiSend<void>('DELETE', `/dataset/cases/${encodeURIComponent(caseId)}`)

// --- evals ---

export const runEval = (request: EvalRunRequest, signal?: AbortSignal) =>
  postSse<EvalProgressEvent>('/evals/run', request, signal)

export const getEvalRun = (runId: number) => apiGet<EvalRun>(`/evals/runs/${runId}`)

export const getEvalRunResults = (runId: number) => apiGet<EvalResult[]>(`/evals/runs/${runId}/results`)

export const updateEvalResult = (resultId: number, update: ManualVerdictUpdate) =>
  apiSend<EvalResult>('PATCH', `/evals/results/${resultId}`, update)

export const getEvalReport = () => apiGet<EvalReportRow[]>('/evals/report')
