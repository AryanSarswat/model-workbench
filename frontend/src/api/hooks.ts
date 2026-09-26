// Shared queries used by the app shell. Pages keep their own hooks in their own folders.
import { useQuery } from '@tanstack/react-query'
import { getHardware, getHfKeyStatus } from './endpoints'

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
