import type { BackendName } from '../api/types'

// The Playground URL that preselects a model; `quant` only applies to GGUF.
export function playgroundPath({ model, backend, quant }: { model: string; backend: BackendName; quant?: string | null }): string {
  const params = new URLSearchParams({ model, backend })
  if (backend === 'gguf' && quant) params.set('quant', quant)
  return `/playground?${params}`
}
