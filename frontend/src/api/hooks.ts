// Shared queries used by the app shell and by more than one page. Page-only hooks stay
// in their page's folder.
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { getHardware, getHfKeyStatus } from './endpoints'
import { getSse } from './sse'
import type { DownloadJob } from './types'

export const queryKeys = {
  hardware: ['config', 'hardware'] as const,
  hfKeyStatus: ['config', 'hf-api-key'] as const,
}

// Hardware doesn't change while the app is open.
export function useHardware() {
  return useQuery({ queryKey: queryKeys.hardware, queryFn: getHardware, staleTime: Infinity })
}

// Invalidate queryKeys.hfKeyStatus after setHfKey so the top bar updates.
export function useHfKeyStatus() {
  return useQuery({ queryKey: queryKeys.hfKeyStatus, queryFn: getHfKeyStatus, staleTime: 60_000 })
}

const RECONNECT_MS = 2000

// Live download jobs from GET /models/downloads/events: every job active when the stream
// opens, then each one's latest state through to completed/failed. `onFinished` runs once
// per job reaching a final state while the page is open. A dropped stream reconnects.
export function useDownloadJobs(onFinished?: (job: DownloadJob) => void): DownloadJob[] {
  const [jobs, setJobs] = useState<ReadonlyMap<number, DownloadJob>>(new Map())
  const onFinishedRef = useRef(onFinished)
  useEffect(() => {
    onFinishedRef.current = onFinished
  })

  useEffect(() => {
    const controller = new AbortController()
    let retry: ReturnType<typeof setTimeout> | undefined
    async function connect() {
      try {
        for await (const job of getSse<DownloadJob>('/models/downloads/events', controller.signal)) {
          setJobs((prev) => new Map(prev).set(job.id, job))
          if (job.status === 'completed' || job.status === 'failed') onFinishedRef.current?.(job)
        }
      } catch {
        // Aborted on unmount, or the stream dropped: reconnect below unless unmounted.
      }
      if (!controller.signal.aborted) retry = setTimeout(() => void connect(), RECONNECT_MS)
    }
    void connect()
    return () => {
      controller.abort()
      clearTimeout(retry)
    }
  }, [])

  return useMemo(() => [...jobs.values()], [jobs])
}

export function isActiveJob(job: DownloadJob): boolean {
  return job.status === 'pending' || job.status === 'downloading'
}
