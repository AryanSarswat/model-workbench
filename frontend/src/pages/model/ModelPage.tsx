import { useParams } from 'react-router'
import { PageHeader } from '../../components/PageHeader'

// Placeholder -- replaced by the model detail screen.
export default function ModelPage() {
  const { author, name } = useParams()
  return (
    <main style={{ padding: '40px 40px 0' }}>
      <PageHeader eyebrow={`Radar / ${author}`} title={name} />
    </main>
  )
}
