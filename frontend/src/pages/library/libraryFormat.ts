// Pure formatting helpers for the Library screen. Not in src/lib because they're
// specific to this screen's presentation (format chip text, tool param summaries).
import type { DownloadedModelRecord, GpuInfo, ToolSpec } from '../../api/types'

// "GGUF · Q4_K_M" (repo prefix and .gguf extension stripped from the quant filename)
// or "transformers snapshot".
export function formatChip(record: DownloadedModelRecord): string {
  if (record.backend === 'transformers') return 'transformers snapshot'
  const quant = record.quant ?? ''
  const withoutExt = quant.replace(/\.gguf$/i, '')
  const repoName = record.repo_id.split('/').pop() ?? ''
  const stripped =
    repoName && withoutExt.startsWith(repoName) ? withoutExt.slice(repoName.length).replace(/^[-_.]+/, '') : withoutExt
  return `GGUF · ${stripped || withoutExt}`
}

// The playground chat link for a downloaded model.
export function chatPath(record: DownloadedModelRecord): string {
  const params = new URLSearchParams({ model: record.repo_id, backend: record.backend })
  if (record.backend === 'gguf' && record.quant) params.set('quant', record.quant)
  return `/playground?${params.toString()}`
}

// "expression: string, timezone?: string" from a ToolSpec's JSON-Schema parameters.
export function summarizeParams(spec: ToolSpec): string {
  const schema = spec.parameters as { properties?: Record<string, { type?: string }>; required?: string[] }
  const properties = schema.properties ?? {}
  const required = new Set(schema.required ?? [])
  return Object.entries(properties)
    .map(([name, prop]) => `${name}${required.has(name) ? '' : '?'}: ${prop.type ?? 'any'}`)
    .join(', ')
}

const GPU_LABELS: Record<GpuInfo['kind'], string> = {
  apple_silicon: 'Apple Silicon',
  nvidia: 'NVIDIA',
  none: 'CPU only',
}

// "Apple Silicon", "CPU only", or the reported GPU name when known.
export function gpuLabel(gpu: GpuInfo): string {
  return gpu.kind === 'nvidia' && gpu.name ? gpu.name : GPU_LABELS[gpu.kind]
}
