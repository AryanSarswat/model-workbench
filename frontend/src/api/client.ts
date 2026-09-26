// JSON fetch helpers. /api is proxied to the FastAPI backend by the Vite dev server.
export const API_BASE = '/api'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

interface ErrorBody {
  // WorkbenchError: {error: {code, message, details}}
  error?: { code?: string; message?: string; details?: Record<string, unknown> }
  // FastAPI's own errors: {detail: "..."} or, for request validation, {detail: [{loc, msg}]}
  detail?: string | { loc?: (string | number)[]; msg?: string }[]
}

// Builds an ApiError from a non-2xx response: the backend's error shape when present,
// else FastAPI's `detail`, else the raw body text or status line.
export async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text().catch(() => '')
  let body: ErrorBody | null = null
  try {
    body = JSON.parse(text) as ErrorBody
  } catch {
    // not JSON (e.g. a proxy error page) -- fall through to the text
  }

  if (body?.error?.message) {
    const { code = 'http_error', message, details = {} } = body.error
    return new ApiError(response.status, code, message, details)
  }
  if (typeof body?.detail === 'string') {
    return new ApiError(response.status, 'http_error', body.detail)
  }
  if (Array.isArray(body?.detail)) {
    const message = body.detail
      .map((d) => [d.loc?.join('.'), d.msg].filter(Boolean).join(': '))
      .join('; ')
    return new ApiError(response.status, 'validation_error', message, { detail: body.detail })
  }
  const fallback = text.trim() || `${response.status} ${response.statusText}`.trim()
  return new ApiError(response.status, 'http_error', `Request failed: ${fallback}`)
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>('GET', path, undefined, signal)
}

export function apiSend<T>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(method, path, body, signal)
}
