import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import PlaygroundPage from './PlaygroundPage'

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

function renderPlayground(initialEntry: string, chatEvents: object[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/models/downloaded') return Response.json([])
    if (url === '/api/tools') return Response.json([{ name: 'calculator', description: 'Evaluate an arithmetic expression', parameters: {} }])
    if (url === '/api/chat/stream' && init?.method === 'POST') return sseResponse(chatEvents)
    return new Response('not mocked', { status: 500 })
  })
  vi.stubGlobal('fetch', fetchMock)

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/playground" element={<PlaygroundPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return fetchMock
}

describe('PlaygroundPage', () => {
  it('sends a message and renders the streamed reply with its metrics', async () => {
    const fetchMock = renderPlayground('/playground?model=Qwen%2FQwen3-14B&backend=api', [
      { delta: 'Hel', done: false, error: null, usage: null, tools_called: [], retries: 0 },
      { delta: 'lo', done: false, error: null, usage: null, tools_called: [], retries: 0 },
      { delta: '', done: true, error: null, usage: { prompt_tokens: 10, completion_tokens: 5 }, tools_called: [], retries: 0 },
    ])

    await screen.findByText('calculator') // tools loaded

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hi there' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('Hello')).toBeInTheDocument()
    expect(screen.getByText('5 tokens')).toBeInTheDocument()
    expect(screen.getByText(/tok\/s/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument() // reverted from Stop

    const chatCall = fetchMock.mock.calls.find(([url]) => url === '/api/chat/stream')
    expect(chatCall).toBeDefined()
    const body = JSON.parse((chatCall?.[1] as RequestInit).body as string) as Record<string, unknown>
    expect(body).toMatchObject({
      model_id: 'Qwen/Qwen3-14B',
      backend: 'api',
      messages: [{ role: 'user', content: 'hi there' }],
      tools: null,
      output_schema: null,
    })
  })

  it('blocks sending when the JSON Schema editor holds invalid JSON', async () => {
    const fetchMock = renderPlayground('/playground?backend=api', [])
    await screen.findByText('calculator')

    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'org/model' } })
    fireEvent.click(screen.getByLabelText('Constrain replies to a JSON Schema'))
    fireEvent.change(screen.getByLabelText('JSON Schema'), { target: { value: '{not json' } })
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hi' } })

    expect(screen.getByText(/^Invalid JSON:/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/chat/stream')).toBe(false)
  })
})
