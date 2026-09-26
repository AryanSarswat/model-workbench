import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { DownloadedModelRecord } from '../../api/types'
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

function renderPlayground(initialEntry: string, chatEvents: object[], downloadedModels: DownloadedModelRecord[] = []) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url === '/api/models/downloaded') return Response.json(downloadedModels)
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
      { delta: 'Hel', done: false, error: null, usage: null, tools_called: [], tool_calls: [], retries: 0 },
      { delta: 'lo', done: false, error: null, usage: null, tools_called: [], tool_calls: [], retries: 0 },
      { delta: '', done: true, error: null, usage: { prompt_tokens: 10, completion_tokens: 5 }, tools_called: [], tool_calls: [], retries: 0 },
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

  it('shows each tool call with its arguments and the result the model was sent back', async () => {
    const url = 'https://www.accuweather.com/en/us/seattle/98104/weather-forecast/351409'
    const page = 'x'.repeat(2000)
    renderPlayground('/playground?model=org%2Fmodel&backend=api', [
      { delta: 'Sorry, I cannot.', done: false, error: null, usage: null, tools_called: [], tool_calls: [], retries: 0 },
      {
        delta: '',
        done: true,
        error: null,
        usage: null,
        tools_called: ['web_fetch', 'web_fetch'],
        tool_calls: [
          { name: 'web_fetch', arguments: { url }, result: 'Error: HTTP Error 403: Forbidden', duration_ms: 412 },
          { name: 'web_fetch', arguments: { url: 'https://example.com/' }, result: page, duration_ms: 700 },
        ],
        retries: 0,
      },
    ])
    await screen.findByText('calculator')

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'weather?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    // A failed call is visibly a failure, with the URL it was asked for -- not just a tool name.
    expect(await screen.findByText(url)).toBeInTheDocument()
    expect(screen.getByText('Error: HTTP Error 403: Forbidden')).toBeInTheDocument()
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(screen.getByText('412 ms')).toBeInTheDocument()

    // A long result is previewed, and the full text the model saw is one click away.
    expect(screen.queryByText(page)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show full result' }))
    expect(screen.getByText(page)).toBeInTheDocument()
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

  it('re-picks a valid gguf model after switching gguf -> api -> gguf, instead of resending the stale api id', async () => {
    const ggufRecord: DownloadedModelRecord = {
      id: 1,
      repo_id: 'Qwen/Qwen3-14B',
      backend: 'gguf',
      quant: 'Q4_K_M.gguf',
      local_path: '/models/qwen',
      size_bytes: 1,
      downloaded_at: '2024-01-01T00:00:00Z',
      last_used_at: null,
    }
    const fetchMock = renderPlayground(
      '/playground',
      [{ delta: 'ok', done: true, error: null, usage: { prompt_tokens: 1, completion_tokens: 1 }, tools_called: [], tool_calls: [], retries: 0 }],
      [ggufRecord],
    )
    await screen.findByText('calculator')

    fireEvent.click(screen.getByRole('button', { name: 'GGUF' }))
    const modelSelect = await screen.findByLabelText<HTMLSelectElement>('Model')
    await screen.findByDisplayValue('Qwen/Qwen3-14B')
    expect(modelSelect.value).toBe('Qwen/Qwen3-14B') // only downloaded quant -> bare repo_id

    fireEvent.click(screen.getByRole('button', { name: 'API' }))
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'org/some-api-model' } })

    fireEvent.click(screen.getByRole('button', { name: 'GGUF' }))
    const modelSelectAgain = await screen.findByLabelText<HTMLSelectElement>('Model')
    expect(modelSelectAgain.value).toBe('Qwen/Qwen3-14B') // re-picked, not left on the stale api id

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hi' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await screen.findByText('ok')
    const chatCall = fetchMock.mock.calls.find(([url]) => url === '/api/chat/stream')
    const body = JSON.parse((chatCall?.[1] as RequestInit).body as string) as Record<string, unknown>
    expect(body).toMatchObject({ model_id: 'Qwen/Qwen3-14B', backend: 'gguf' })
  })
})
