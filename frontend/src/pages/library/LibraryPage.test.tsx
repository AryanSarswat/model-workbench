import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DownloadedModelRecord, DownloadJob, HardwareInfo } from '../../api/types'
import { sseStream } from '../../test/sseStream'
import LibraryPage from './LibraryPage'

const hardware: HardwareInfo = {
  platform: 'darwin',
  arch: 'arm64',
  total_ram_gb: 18,
  gpu: { kind: 'apple_silicon', name: null, vram_gb: null },
  usable_memory_gb: 18,
}

const downloaded: DownloadedModelRecord = {
  id: 1,
  repo_id: 'Qwen/Qwen3-14B',
  backend: 'gguf',
  quant: 'Qwen3-14B-Q4_K_M.gguf',
  local_path: '/models/Qwen3-14B-Q4_K_M.gguf',
  size_bytes: 9 * 1024 ** 3,
  downloaded_at: '2026-09-20T00:00:00Z',
  last_used_at: null,
  unsupported_reason: null,
}

function renderLibrary(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal('fetch', fetchMock)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

function routeResponses(overrides: Record<string, Response> = {}) {
  const base: Record<string, Response> = {
    '/api/config/hardware': Response.json(hardware),
    '/api/config/hf-api-key': Response.json({ is_set: false }),
    '/api/models/downloaded': Response.json([downloaded]),
    '/api/models/downloads/events': sseStream().response,
    '/api/tools': Response.json([]),
  }
  return { ...base, ...overrides }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LibraryPage', () => {
  it('deletes a downloaded model only after the user confirms', async () => {
    const responses = routeResponses()
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') return new Response(null, { status: 204 })
      return responses[url] ?? new Response('not mocked', { status: 500 })
    })
    renderLibrary(fetchMock)

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Qwen/Qwen3-14B' }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/models/downloaded/1'), expect.anything())

    confirmSpy.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Delete Qwen/Qwen3-14B' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/models/downloaded/1', expect.objectContaining({ method: 'DELETE' })),
    )
  })

  it('saves the HF key without ever rendering its value', async () => {
    const responses = routeResponses()
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/config/hf-api-key' && init?.method === 'POST') {
        return Response.json({ is_set: true })
      }
      return responses[url] ?? new Response('not mocked', { status: 500 })
    })
    renderLibrary(fetchMock)

    const input = await screen.findByLabelText('Token')
    fireEvent.change(input, { target: { value: 'hf_super_secret_token' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Save' })[0])

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/config/hf-api-key',
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ api_key: 'hf_super_secret_token' }) }),
      ),
    )
    await waitFor(() => expect(input).toHaveValue(''))
    expect(screen.queryByText('hf_super_secret_token')).not.toBeInTheDocument()
    expect(screen.getByDisplayValue('')).toBe(input)
  })

  it('does not show the empty state or a model count while downloaded models are still loading', async () => {
    let resolveDownloaded: (response: Response) => void = () => {}
    const downloadedPromise = new Promise<Response>((resolve) => {
      resolveDownloaded = resolve
    })
    const responses = routeResponses()
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/models/downloaded') return downloadedPromise
      return responses[url] ?? new Response('not mocked', { status: 500 })
    })
    renderLibrary(fetchMock)

    await screen.findByText('On disk')
    expect(screen.queryByText(/Nothing downloaded yet/)).not.toBeInTheDocument()
    expect(screen.queryByText(/models? ·/)).not.toBeInTheDocument()

    resolveDownloaded(Response.json([]))
    expect(await screen.findByText(/Nothing downloaded yet/)).toBeInTheDocument()
    expect(await screen.findByText('0 models · 0.0 GB')).toBeInTheDocument()
  })

  it('shows a download while it runs, then its error when the stream reports it failed', async () => {
    const failedJob: DownloadJob = {
      id: 42,
      repo_id: 'org/broken-model',
      kind: 'gguf',
      filename: 'model.gguf',
      current_file: null,
      status: 'failed',
      percent: 30,
      detail: 'download failed',
      error: 'Connection reset by peer',
      downloaded_model_id: null,
      created_at: '2026-09-25T00:00:00Z',
      updated_at: '2026-09-25T00:00:05Z',
    }
    const stream = sseStream()
    const responses = routeResponses({
      '/api/models/downloaded': Response.json([]),
      '/api/models/downloads/events': stream.response,
    })
    renderLibrary(vi.fn(async (url: string) => responses[url] ?? new Response('not mocked', { status: 500 })))

    stream.send({ ...failedJob, status: 'downloading', error: null })
    expect(await screen.findByText('org/broken-model')).toBeInTheDocument()

    stream.send(failedJob)
    expect(await screen.findByText(/Connection reset by peer/)).toBeInTheDocument()
  })
})
