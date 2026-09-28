// Pure formatting helpers for the Library screen. Not in src/lib because they're
// specific to this screen's presentation (format chip text, tool param summaries).
import type { DownloadedModelRecord, ToolSpec } from '../../api/types'

// "GGUF · Q4_K_M" (repo prefix and .gguf extension stripped from the quant filename)
// or "transformers snapshot".
export function formatChip(record: DownloadedModelRecord): string {
  if (record.backend === 'transformers') return 'transformers snapshot'
  const quant = record.quant ?? ''
  const withoutExt = quant.replace(/\.gguf$/i, '')
  // "Org/Model-GGUF" repos usually name files "model-<quant>", in any case.
  const modelName = (record.repo_id.split('/').pop() ?? '').replace(/-gguf$/i, '')
  const stripped =
    modelName && withoutExt.toLowerCase().startsWith(modelName.toLowerCase())
      ? withoutExt.slice(modelName.length).replace(/^[-_.]+/, '')
      : withoutExt
  return `GGUF · ${stripped || withoutExt}`
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
