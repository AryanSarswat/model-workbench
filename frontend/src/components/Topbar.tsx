import { Link, useLocation } from 'react-router'
import { useHardware, useHfKeyStatus } from '../api/hooks'
import type { GpuInfo } from '../api/types'
import styles from './Topbar.module.css'

// `match` decides the active tab: a model page belongs to Radar, a run review to Evals.
const TABS = [
  { label: 'Radar', to: '/', match: (path: string) => path === '/' || path.startsWith('/models/') },
  { label: 'Playground', to: '/playground', match: (path: string) => path === '/playground' },
  { label: 'Evals', to: '/evals', match: (path: string) => path === '/evals' || path.startsWith('/evals/') },
  { label: 'Dataset', to: '/dataset', match: (path: string) => path === '/dataset' },
  { label: 'Library', to: '/library', match: (path: string) => path === '/library' },
]

const GPU_LABELS: Record<GpuInfo['kind'], string> = { apple_silicon: 'Apple Silicon', nvidia: 'NVIDIA', none: 'CPU only' }

export function Topbar() {
  const { pathname } = useLocation()
  return (
    <header className={styles.bar}>
      <Link to="/" className={styles.brand}>
        workbench
      </Link>
      <nav aria-label="Primary" className={styles.nav}>
        {TABS.map((tab) => (
          <Link
            key={tab.to}
            to={tab.to}
            className={styles.tab}
            aria-current={tab.match(pathname) ? 'page' : undefined}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      <div className={styles.meta}>
        <HardwareSummary />
        <HfKeyStatus />
      </div>
    </header>
  )
}

function HardwareSummary() {
  const { data, isPending, isError } = useHardware()
  if (isPending) return <span>Detecting hardware…</span>
  if (isError) return <span>Hardware unavailable</span>
  const gpu = data.gpu.kind === 'nvidia' && data.gpu.name ? data.gpu.name : GPU_LABELS[data.gpu.kind]
  return (
    <>
      <span>{[data.platform, data.arch, gpu].join(' · ')}</span>
      <span className={styles.strong}>{data.usable_memory_gb.toFixed(1)} GB usable</span>
    </>
  )
}

function HfKeyStatus() {
  const { data, isError } = useHfKeyStatus()
  if (isError) return <span>HF key unknown</span>
  if (!data) return null
  return (
    <span className={styles.key}>
      <span className={data.is_set ? styles.dotSet : styles.dotUnset} aria-hidden="true" />
      {data.is_set ? 'HF key set' : 'HF key not set'}
    </span>
  )
}
