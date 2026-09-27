import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routes } from './routes'

vi.mock('./pages/library/LibraryPage', () => ({
  default: () => {
    throw new Error('Library exploded')
  },
}))

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderAt(path: string) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('not mocked', { status: 500 })))
  vi.spyOn(console, 'error').mockImplementation(() => {}) // React logs the caught error
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />
    </QueryClientProvider>,
  )
}

describe('routes', () => {
  it("shows a crashing page's error inside the app shell, so navigation still works", async () => {
    renderAt('/library')

    expect(await screen.findByRole('alert')).toHaveTextContent('Library exploded')
    expect(screen.getByRole('link', { name: 'Playground' })).toBeInTheDocument()
  })
})
