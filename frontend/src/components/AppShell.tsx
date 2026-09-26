import { Outlet } from 'react-router'
import styles from './AppShell.module.css'
import { Topbar } from './Topbar'

// Top bar over the routed page. Pages render their own <main>.
export function AppShell() {
  return (
    <div className={styles.shell}>
      <Topbar />
      <Outlet />
    </div>
  )
}
