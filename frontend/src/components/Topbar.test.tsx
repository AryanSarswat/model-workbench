import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { HardwareInfo } from '../api/types'
import { routes } from '../routes'

const hardware: HardwareInfo = {
  platform: 'darwin',
  arch: 'arm64',
  total_ram_gb: 18,
  gpu: { kind: 'apple_silicon', name: null, vram_gb: null },
  usable_memory_gb: 18,
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

describe('Topbar', () => {
  it('marks the section tab of nested routes as current', () => {
    renderAt('/evals/runs/42', {})

    const nav = screen.getByRole('navigation', { name: 'Primary' })
    const current = nav.querySelectorAll('[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0]).toHaveTextContent('Evals')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Run 42')
  })

  it('shows the detected hardware and HF key status from the API', async () => {
    renderAt('/', {
      '/api/config/hardware': Response.json(hardware),
      '/api/config/hf-api-key': Response.json({ is_set: false }),
    })

    expect(await screen.findByText('darwin · arm64 · Apple Silicon')).toBeInTheDocument()
    expect(screen.getByText('18.0 GB usable')).toBeInTheDocument()
    expect(await screen.findByText('HF key not set')).toBeInTheDocument()
  })

  it('degrades to a notice when hardware detection fails', async () => {
    renderAt('/', {})

    expect(await screen.findByText('Hardware unavailable')).toBeInTheDocument()
  })
})
