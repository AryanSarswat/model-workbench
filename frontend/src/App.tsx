import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { routes } from './routes'

// One retry: the backend is local, so a failure is rarely transient.
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } })
const router = createBrowserRouter(routes)

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
