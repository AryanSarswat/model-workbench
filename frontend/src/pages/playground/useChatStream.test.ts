import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { BackendName } from '../../api/types'
import { useChatStream, type SendMessageOptions } from './useChatStream'

function sseResponse(events: object[]): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
      controller.close()
    },
  })
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

const options: SendMessageOptions = { modelId: 'gpt2', backend: 'api' as BackendName, systemPrompt: '', tools: [], outputSchema: null }

describe('useChatStream', () => {
  it('settles a turn on its error chunk and excludes it from the next turn\'s resend history', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse([{ delta: '', done: false, error: 'boom', usage: null, tools_called: [], tool_calls: [], retries: 0 }]))
      .mockResolvedValueOnce(
        sseResponse([{ delta: 'ok', done: true, error: null, usage: { prompt_tokens: 1, completion_tokens: 1 }, tools_called: [], tool_calls: [], retries: 0 }]),
      )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatStream())

    await act(async () => {
      await result.current.sendMessage('first', options)
    })

    expect(result.current.turns).toHaveLength(2)
    expect(result.current.turns[1]).toMatchObject({ streaming: false, error: expect.any(Error) })

    await act(async () => {
      await result.current.sendMessage('second', options)
    })

    expect(result.current.turns).toHaveLength(4)
    const secondCall = fetchMock.mock.calls[1] as [string, RequestInit]
    const body = JSON.parse(secondCall[1].body as string) as { messages: unknown[] }
    // The errored first turn (and its user message) is left out of the resend.
    expect(body.messages).toEqual([{ role: 'user', content: 'second' }])
  })

  it('settles a turn with an error when the stream ends without a done or error chunk', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(sseResponse([{ delta: 'partial', done: false, error: null, usage: null, tools_called: [], tool_calls: [], retries: 0 }])))

    const { result } = renderHook(() => useChatStream())

    await act(async () => {
      await result.current.sendMessage('hi', options)
    })

    expect(result.current.turns[1]).toMatchObject({ streaming: false, content: 'partial', error: expect.any(Error) })
  })
})
