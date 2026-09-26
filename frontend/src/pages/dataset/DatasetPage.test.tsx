import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from '../../routes'
import type { HardwareInfo, TestCase } from '../../api/types'
import DatasetPage from './DatasetPage'

const hardware: HardwareInfo = {
  platform: 'darwin',
  arch: 'arm64',
  total_ram_gb: 18,
  gpu: { kind: 'apple_silicon', name: null, vram_gb: null },
  usable_memory_gb: 18,
}

function renderDataset(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal('fetch', fetchMock)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DatasetPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// Renders the full route table (AppShell + DatasetPage) through the real data router --
// unlike plain MemoryRouter, this applies URL changes asynchronously (inside
// startTransition), which is what exposed the Duplicate bug below.
function renderDatasetRoute(fetchMock: ReturnType<typeof vi.fn>, initialEntry: string) {
  vi.stubGlobal('fetch', fetchMock)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter(routes, { initialEntries: [initialEntry] })
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('DatasetPage', () => {
  it('points at the template file when the dataset is empty', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/dataset/cases') return Response.json([])
      if (url === '/api/tools') return Response.json([])
      return new Response('not mocked', { status: 500 })
    })
    renderDataset(fetchMock)

    expect(await screen.findByText(/data\/test_cases\.template\.json/)).toBeInTheDocument()
  })

  it('POSTs the case built from the form when saving a new case', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/dataset/cases' && init?.method === 'POST') {
        return Response.json(JSON.parse(init.body as string), { status: 201 })
      }
      if (url === '/api/dataset/cases') return Response.json([])
      if (url === '/api/tools') return Response.json([])
      return new Response('not mocked', { status: 500 })
    })
    renderDataset(fetchMock)

    fireEvent.click(await screen.findByRole('button', { name: /New case/ }))

    fireEvent.change(await screen.findByLabelText('ID'), { target: { value: 'coding-001' } })
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'coding' } })
    fireEvent.change(screen.getByLabelText('Message 1 content'), { target: { value: 'Write fib(n).' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/dataset/cases', expect.objectContaining({ method: 'POST' })),
    )
    const [, init] = fetchMock.mock.calls.find(([url, i]) => url === '/api/dataset/cases' && i?.method === 'POST')!
    const body = JSON.parse(init!.body as string)
    expect(body).toMatchObject({
      id: 'coding-001',
      category: 'coding',
      messages: [{ role: 'user', content: 'Write fib(n).' }],
      system_prompt: null,
      judge: null,
      tags: [],
    })
  })

  it('shows a 409 conflict from the API instead of silently failing', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/dataset/cases' && init?.method === 'POST') {
        return Response.json(
          { error: { code: 'test_case_already_exists', message: "Test case with id 'coding-001' already exists." } },
          { status: 409 },
        )
      }
      if (url === '/api/dataset/cases') return Response.json([])
      if (url === '/api/tools') return Response.json([])
      return new Response('not mocked', { status: 500 })
    })
    renderDataset(fetchMock)

    fireEvent.click(await screen.findByRole('button', { name: /New case/ }))
    fireEvent.change(await screen.findByLabelText('ID'), { target: { value: 'coding-001' } })
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'coding' } })
    fireEvent.change(screen.getByLabelText('Message 1 content'), { target: { value: 'hi' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText(/already exists/)).toBeInTheDocument()
  })

  // Regression test for a HIGH-severity bug: the data router (unlike plain MemoryRouter)
  // applies URL changes asynchronously inside startTransition. The old implementation kept
  // a `loadedCaseKey` piece of state that it synced to the URL's `case` param during render;
  // clicking Duplicate raced that sync and the draft got clobbered back to the original
  // case, then to a blank form once the URL caught up. Must run through the real data
  // router (createMemoryRouter/RouterProvider) to reproduce -- plain MemoryRouter applies
  // search-param updates synchronously and would pass even with the old, buggy code.
  it('duplicate opens a prefilled -copy draft, not the original or a blank one', async () => {
    const seedCase: TestCase = {
      id: 'coding-001',
      category: 'coding',
      messages: [{ role: 'user', content: 'Write fib(n).' }],
      system_prompt: null,
      output_schema: null,
      expected_tools: null,
      assertions: [],
      judge: null,
      tags: ['python'],
    }
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/dataset/cases') return Response.json([seedCase])
      if (url === '/api/tools') return Response.json([])
      if (url === '/api/config/hardware') return Response.json(hardware)
      if (url === '/api/config/hf-api-key') return Response.json({ is_set: false })
      return new Response('not mocked', { status: 500 })
    })
    renderDatasetRoute(fetchMock, '/dataset?category=coding&case=coding-001')

    const idField = await screen.findByLabelText('ID')
    await waitFor(() => expect(idField).toHaveValue('coding-001'))

    fireEvent.click(screen.getByRole('button', { name: 'Duplicate' }))

    await waitFor(() => expect(screen.getByLabelText('ID')).toHaveValue('coding-001-copy'))
    expect(screen.getByLabelText('ID')).not.toHaveAttribute('readonly')
    expect(screen.getByLabelText('Category')).toHaveValue('coding')
    expect(screen.getByLabelText('Message 1 content')).toHaveValue('Write fib(n).')
    expect(screen.getByLabelText('Tags')).toHaveValue('python')
  })
})
