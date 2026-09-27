import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { DownloadJob, DownloadedModelRecord, FeasibilityReport, HardwareInfo, ModelDetail } from '../../api/types'
import { routes } from '../../routes'
import { sseStream } from '../../test/sseStream'

const hardware: HardwareInfo = {
  platform: 'darwin',
  arch: 'arm64',
  total_ram_gb: 18,
  gpu: { kind: 'apple_silicon', name: null, vram_gb: null },
  usable_memory_gb: 18,
}

const detail: ModelDetail = {
  id: 'Qwen/Qwen3-14B',
  author: 'Qwen',
  pipeline_tag: 'text-generation',
  downloads: 612304,
  likes: 1402,
  trending_score: 1,
  created_at: '2026-09-20T00:00:00Z',
  gated: false,
  tags: ['text-generation'],
  library_name: 'transformers',
  gguf_files: [
    { filename: 'Qwen3-14B-Q3_K_M.gguf', size_bytes: 7_300_000_000 },
    { filename: 'Qwen3-14B-Q4_K_M.gguf', size_bytes: 9_000_000_000 },
    { filename: 'Qwen3-14B-Q5_K_M.gguf', size_bytes: 10_500_000_000 },
  ],
  parameter_count: 14_800_000_000,
  dtype: 'BF16',
}

const feasibility: FeasibilityReport = {
  available_memory_gb: 18,
  comfortable_fraction: 0.7,
  tight_fraction: 0.95,
  options: [
    { label: 'Qwen3-14B-Q3_K_M.gguf', backend: 'gguf', filename: 'Qwen3-14B-Q3_K_M.gguf', verdict: 'comfortable', estimated_memory_gb: 8.8, reason: 'should run comfortably.' },
    { label: 'Qwen3-14B-Q4_K_M.gguf', backend: 'gguf', filename: 'Qwen3-14B-Q4_K_M.gguf', verdict: 'comfortable', estimated_memory_gb: 10.8, reason: 'should run comfortably.' },
    { label: 'Qwen3-14B-Q5_K_M.gguf', backend: 'gguf', filename: 'Qwen3-14B-Q5_K_M.gguf', verdict: 'tight', estimated_memory_gb: 12.6, reason: 'little headroom.' },
  ],
}

const downloadedRecord: DownloadedModelRecord = {
  id: 1,
  repo_id: 'Qwen/Qwen3-14B',
  backend: 'gguf',
  model_id: 'Qwen/Qwen3-14B',
  quant: 'Qwen3-14B-Q4_K_M.gguf',
  local_path: '/models/Qwen3-14B-Q4_K_M.gguf',
  size_bytes: 9_000_000_000,
  downloaded_at: '2026-09-21T00:00:00Z',
  last_used_at: null,
  unsupported_reason: null,
}

const activeJob: DownloadJob = {
  id: 7,
  repo_id: 'Qwen/Qwen3-14B',
  kind: 'gguf',
  filename: 'Qwen3-14B-Q5_K_M.gguf',
  current_file: null,
  status: 'downloading',
  percent: 62,
  detail: '',
  error: null,
  downloaded_model_id: null,
  created_at: '2026-09-21T00:00:00Z',
  updated_at: '2026-09-21T00:00:00Z',
}

function renderModel(responses: Record<string, Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => responses[url] ?? new Response('not mocked', { status: 500 })),
  )
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/models/Qwen/Qwen3-14B'] })} />
    </QueryClientProvider>,
  )
}

// An event stream that sends `jobs` and then stays open, like the real endpoint.
function jobsStream(...jobs: DownloadJob[]): Response {
  const stream = sseStream()
  jobs.forEach(stream.send)
  return stream.response
}

function renderWithFetch(fetchImpl: (url: string) => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(fetchImpl))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/models/Qwen/Qwen3-14B'] })} />
    </QueryClientProvider>,
  )
}

const commonResponses = {
  '/api/config/hardware': () => Response.json(hardware),
  '/api/config/hf-api-key': () => Response.json({ is_set: false }),
  '/api/models/Qwen/Qwen3-14B': () => Response.json(detail),
  '/api/models/Qwen/Qwen3-14B/feasibility': () => Response.json(feasibility),
  '/api/evals/report': () => Response.json([]),
}

function withCommon(overrides: Record<string, Response>): Record<string, Response> {
  const base: Record<string, Response> = {}
  for (const [url, make] of Object.entries(commonResponses)) base[url] = make()
  return { ...base, ...overrides }
}

describe('ModelPage', () => {
  it('shows On disk for a downloaded quant and live progress for a downloading one', async () => {
    renderModel(
      withCommon({
        '/api/models/downloaded': Response.json([downloadedRecord]),
        '/api/models/downloads/events': jobsStream(activeJob),
      }),
    )

    expect(await screen.findByRole('link', { name: /On disk · Chat/ })).toHaveAttribute(
      'href',
      '/playground?model=Qwen%2FQwen3-14B&backend=gguf&quant=Qwen3-14B-Q4_K_M.gguf',
    )
    expect(await screen.findByText('Downloading 62%')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Qwen3-14B-Q5_K_M.gguf download progress' })).toHaveAttribute(
      'aria-valuenow',
      '62',
    )
    // The third option has neither a record nor an active job, so it's still an idle Download button.
    expect(screen.getByRole('button', { name: 'Download' })).toBeInTheDocument()
  })

  it('opens a model whose Hub id has no author, like gpt2', async () => {
    const gpt2: ModelDetail = { ...detail, id: 'gpt2', gguf_files: [] }
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/models/gpt2') return Response.json(gpt2)
      if (url === '/api/models/gpt2/feasibility') return Response.json({ ...feasibility, options: [] })
      if (url === '/api/models/downloads/events') return jobsStream()
      return withCommon({ '/api/models/downloaded': Response.json([]) })[url] ?? new Response('not mocked', { status: 500 })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/models/gpt2'] })} />
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'gpt2' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/models/gpt2', expect.anything())
  })

  it('POSTs the right body when Download is clicked', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/models/Qwen/Qwen3-14B/download') {
        return Response.json({ id: 9, repo_id: 'Qwen/Qwen3-14B', kind: 'gguf' }, { status: 202 })
      }
      const responses = withCommon({
        '/api/models/downloaded': Response.json([]),
        '/api/models/downloads/events': jobsStream(),
      })
      return responses[url] ?? new Response('not mocked', { status: 500 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/models/Qwen/Qwen3-14B'] })} />
      </QueryClientProvider>,
    )

    const downloadButtons = await screen.findAllByRole('button', { name: 'Download' })
    fireEvent.click(downloadButtons[0])

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/models/Qwen/Qwen3-14B/download',
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ filename: 'Qwen3-14B-Q3_K_M.gguf' }) }),
      ),
    )
  })

  it('flips a row to On disk · Chat when the stream reports its job completed', async () => {
    const stream = sseStream()
    let downloadedCalls = 0
    renderWithFetch(async (url: string) => {
      if (url === '/api/models/downloads/events') return stream.response
      if (url === '/api/models/downloaded') {
        downloadedCalls += 1
        return Response.json(downloadedCalls === 1 ? [] : [downloadedRecord])
      }
      return withCommon({})[url] ?? new Response('not mocked', { status: 500 })
    })

    stream.send(activeJob)
    expect(await screen.findByText('Downloading 62%')).toBeInTheDocument()

    // Completion refetches the downloaded list, so the row flips over.
    stream.send({ ...activeJob, status: 'completed', percent: 100 })
    expect(await screen.findByRole('link', { name: /On disk · Chat/ })).toHaveAttribute(
      'href',
      '/playground?model=Qwen%2FQwen3-14B&backend=gguf&quant=Qwen3-14B-Q4_K_M.gguf',
    )
  })

  it('surfaces a failed download error from the stream', async () => {
    const stream = sseStream()
    renderWithFetch(async (url: string) => {
      if (url === '/api/models/downloads/events') return stream.response
      return withCommon({ '/api/models/downloaded': Response.json([]) })[url] ?? new Response('not mocked', { status: 500 })
    })

    stream.send(activeJob)
    expect(await screen.findByText('Downloading 62%')).toBeInTheDocument()
    stream.send({ ...activeJob, status: 'failed', percent: 40, error: 'Disk full' })
    expect(await screen.findByText(/Disk full/)).toBeInTheDocument()
  })
})
