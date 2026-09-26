import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './client'
import { postSse } from './sse'

// A streaming 200 response whose body arrives as the given text chunks. With `hang`, the
// stream stays open after the last chunk, like a model still generating.
function sseResponse(chunks: string[], hang = false) {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      if (!hang) controller.close()
    },
  })
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

async function collect<T>(events: AsyncGenerator<T>): Promise<T[]> {
  const out: T[] = []
  for await (const event of events) out.push(event)
  return out
}

describe('postSse', () => {
  it('reassembles events split across chunk boundaries', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'data: {"delta":"Hel',
          'lo","done":false}\n',
          '\n: heartbeat\n\ndata: {"delta":"!",',
          '"done":false}\r\n\r',
          '\ndata: {"delta":"","done":true}\n\n',
        ]),
      ),
    )

    const events = await collect(postSse<{ delta: string; done: boolean }>('/chat/stream', {}))

    expect(events).toEqual([
      { delta: 'Hello', done: false },
      { delta: '!', done: false },
      { delta: '', done: true },
    ])
  })

  it('stops with an AbortError when the signal aborts mid-stream', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse(['data: {"n":1}\n\n'], true)))
    const controller = new AbortController()
    const received: unknown[] = []

    const run = (async () => {
      for await (const event of postSse('/evals/run', {}, controller.signal)) {
        received.push(event)
        controller.abort()
      }
    })()

    await expect(run).rejects.toMatchObject({ name: 'AbortError' })
    expect(received).toEqual([{ n: 1 }])
  })

  it('throws ApiError before streaming when the request is rejected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ error: { code: 'missing_api_key', message: 'No HF API key set.', details: {} } }, { status: 400 }),
      ),
    )

    const error = await collect(postSse('/chat/stream', {})).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 400, code: 'missing_api_key' })
  })
})
