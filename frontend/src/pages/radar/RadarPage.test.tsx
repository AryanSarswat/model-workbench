import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { DiscoveredModel, FeasibilityReport, HardwareInfo } from '../../api/types'
import { routes } from '../../routes'

const hardware: HardwareInfo = {
  platform: 'darwin',
  arch: 'arm64',
  total_ram_gb: 18,
  gpu: { kind: 'apple_silicon', name: null, vram_gb: null },
  usable_memory_gb: 18,
}

const model: DiscoveredModel = {
  id: 'Qwen/Qwen3-14B',
  author: 'Qwen',
  pipeline_tag: 'text-generation',
  downloads: 612304,
  likes: 1402,
  trending_score: 1,
  created_at: '2026-09-20T00:00:00Z',
  gated: false,
  tags: [],
  library_name: 'transformers',
}

const feasibility: FeasibilityReport = {
  available_memory_gb: 18,
  options: [
    {
      label: 'Qwen3-14B-Q4_K_M.gguf',
      verdict: 'comfortable',
      estimated_memory_gb: 10.8,
      reason: '~10.8GB needed, 18GB available -- should run comfortably.',
    },
  ],
}

function renderAt(path: string, responses: Record<string, Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => responses[url] ?? new Response('not mocked', { status: 500 })),
  )
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />
    </QueryClientProvider>,
  )
}

describe('RadarPage', () => {
  it('marks a row Estimating while feasibility loads, then renders its verdict', async () => {
    renderAt('/', {
      '/api/config/hardware': Response.json(hardware),
      '/api/config/hf-api-key': Response.json({ is_set: false }),
      '/api/models/discover?sort=trending&limit=20': Response.json([model]),
      '/api/models/Qwen/Qwen3-14B/feasibility': Response.json(feasibility),
    })

    expect(await screen.findByText('Estimating')).toBeInTheDocument()
    expect(await screen.findByText('Fits')).toBeInTheDocument()
    expect(screen.getByText('10.8 GB · 1 option')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Qwen\/Qwen3-14B/ })).toHaveAttribute('href', '/models/Qwen/Qwen3-14B')
  })

  it('shows a short reason and an Unknown chip when feasibility fails', async () => {
    renderAt('/', {
      '/api/config/hardware': Response.json(hardware),
      '/api/config/hf-api-key': Response.json({ is_set: false }),
      '/api/models/discover?sort=trending&limit=20': Response.json([model]),
      '/api/models/Qwen/Qwen3-14B/feasibility': Response.json(
        { error: { code: 'feasibility_unknown', message: 'no data' } },
        { status: 422 },
      ),
    })

    expect(await screen.findByText('Unknown')).toBeInTheDocument()
    expect(screen.getAllByText('No size data available')).toHaveLength(2)
  })
})
