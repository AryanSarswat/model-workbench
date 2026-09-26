import { API_BASE, ApiError, toApiError } from './client'

// POSTs `body` and yields each SSE event's `data:` payload parsed as JSON. EventSource
// can't POST, so this reads the fetch body stream and does the SSE framing itself.
// A non-2xx response throws ApiError before anything is yielded; aborting `signal`
// makes the iteration throw the abort reason (an AbortError).
export async function* postSse<T>(path: string, body: unknown, signal?: AbortSignal): AsyncGenerator<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await toApiError(response)
  if (!response.body) throw new ApiError(response.status, 'empty_stream', 'The server sent no stream body.')

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  // Cancelling unblocks a pending read; throwIfAborted below turns that into an error.
  const onAbort = () => void reader.cancel().catch(() => {})
  signal?.addEventListener('abort', onAbort, { once: true })
  let buffer = ''
  try {
    for (;;) {
      const { value, done } = await reader.read()
      signal?.throwIfAborted()
      if (done) break
      // Normalize after concatenating, so a \r\n split across chunks still collapses.
      buffer = (buffer + value).replace(/\r\n/g, '\n')
      let end: number
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const data = eventData(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        if (data !== null) yield JSON.parse(data) as T
      }
    }
    const data = eventData(buffer) // a final event with no trailing blank line
    if (data !== null) yield JSON.parse(data) as T
  } finally {
    signal?.removeEventListener('abort', onAbort)
    reader.cancel().catch(() => {})
  }
}

// The joined `data:` lines of one event, or null for events without data (comments,
// heartbeats).
function eventData(event: string): string | null {
  const lines = event
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(line.startsWith('data: ') ? 6 : 5))
  return lines.length ? lines.join('\n') : null
}
