// Shared queries used by the app shell and by more than one page. Page-only hooks stay
// in their page's folder.
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { getBackends, getHardware, getHfKeyStatus, listDownloaded, listTools } from './endpoints'
import { getSse } from './sse'
import type { DownloadJob } from './types'

// One key per resource, so a change made on one page (a delete, a finished download,
// a tools reload) refreshes every page that shows it.
export const queryKeys = {
  hardware: ['config', 'hardware'] as const,
  hfKeyStatus: ['config', 'hf-api-key'] as const,
  downloadedModels: ['models', 'downloaded'] as const,
  tools: ['tools'] as const,
  backends: ['backends'] as const,
}

// Hardware doesn't change while the app is open.
export function useHardware() {
  return useQuery({ queryKey: queryKeys.hardware, queryFn: getHardware, staleTime: Infinity })
}

// Backend capabilities and availability are fixed for the server process's lifetime.
export function useBackends() {
  return useQuery({ queryKey: queryKeys.backends, queryFn: getBackends, staleTime: Infinity })
}

// Invalidate queryKeys.hfKeyStatus after setHfKey so the top bar updates.
export function useHfKeyStatus() {
  return useQuery({ queryKey: queryKeys.hfKeyStatus, queryFn: getHfKeyStatus, staleTime: 60_000 })
}

export function useDownloadedModels() {
  return useQuery({ queryKey: queryKeys.downloadedModels, queryFn: listDownloaded })
}

export function useTools() {
  return useQuery({ queryKey: queryKeys.tools, queryFn: listTools })
}

const RECONNECT_MS = 2000

// Live download jobs from GET /models/downloads/events: every job active when the stream
// opens, then each one's latest state through to completed/failed. A completed job
// refreshes the downloaded-models list. A dropped stream reconnects.
export function useDownloadJobs(): DownloadJob[] {
  const queryClient = useQueryClient()
  const [jobs, setJobs] = useState<ReadonlyMap<number, DownloadJob>>(new Map())

  useEffect(() => {
    const controller = new AbortController()
    let retry: ReturnType<typeof setTimeout> | undefined
    async function connect() {
      try {
        for await (const job of getSse<DownloadJob>('/models/downloads/events', controller.signal)) {
          setJobs((prev) => new Map(prev).set(job.id, job))
          if (job.status === 'completed') void queryClient.invalidateQueries({ queryKey: queryKeys.downloadedModels })
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
  }, [queryClient])

  return useMemo(() => [...jobs.values()], [jobs])
}

export function isActiveJob(job: DownloadJob): boolean {
  return job.status === 'pending' || job.status === 'downloading'
}
