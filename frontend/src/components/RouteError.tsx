import { useRouteError } from 'react-router'
import { Button } from './Button'
import { ErrorNotice } from './ErrorNotice'
import { PageHeader } from './PageHeader'

// Shown in place of a page (or the whole shell) that threw while rendering, instead of
// React Router's developer error screen.
export function RouteError() {
  const error = useRouteError()
  return (
    <main className="message-page">
      <PageHeader
        eyebrow="Error"
        title="Something went wrong"
        actions={<Button onClick={() => window.location.reload()}>Reload</Button>}
      />
      <ErrorNotice error={error} />
    </main>
  )
}
