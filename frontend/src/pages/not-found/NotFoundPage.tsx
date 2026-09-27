import { Button } from '../../components/Button'
import { PageHeader } from '../../components/PageHeader'

export default function NotFoundPage() {
  return (
    <main className="message-page">
      <PageHeader eyebrow="404" title="Page not found" actions={<Button to="/">Back to Radar</Button>} />
    </main>
  )
}
