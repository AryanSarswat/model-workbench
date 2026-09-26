import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DownloadedModelRecord, HardwareInfo } from '../../api/types'
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
}

function routeResponses(overrides: Record<string, Response> = {}) {
  const base: Record<string, Response> = {
    '/api/config/hardware': Response.json(hardware),
    '/api/config/hf-api-key': Response.json({ is_set: false }),
    '/api/models/downloaded': Response.json([downloaded]),
    '/api/models/downloads?active=true': Response.json([]),
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
})
