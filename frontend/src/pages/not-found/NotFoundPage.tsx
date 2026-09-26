import { Button } from '../../components/Button'
import { PageHeader } from '../../components/PageHeader'

export default function NotFoundPage() {
  return (
    <main style={{ padding: '40px 40px 0' }}>
      <PageHeader eyebrow="404" title="Page not found" actions={<Button to="/">Back to Radar</Button>} />
    </main>
  )
}
