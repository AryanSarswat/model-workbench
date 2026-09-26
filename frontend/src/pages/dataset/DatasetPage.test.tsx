import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DatasetPage from './DatasetPage'

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
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'Write fib(n).' } })
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
    fireEvent.change(screen.getByLabelText('Content'), { target: { value: 'hi' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText(/already exists/)).toBeInTheDocument()
  })
})
