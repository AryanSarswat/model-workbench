import { useParams } from 'react-router'
import { PageHeader } from '../../components/PageHeader'

// Placeholder -- replaced by the eval run review screen.
export default function ReviewPage() {
  const { runId } = useParams()
  return (
    <main style={{ padding: '40px 40px 0' }}>
      <PageHeader eyebrow="Evals" title={`Run ${runId}`} />
    </main>
  )
}
