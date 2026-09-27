import type { BackendName, StructuredOutputMode } from '../api/types'
import type { ChipTone } from '../components/Chip'

// Presentation only: what each backend can do comes from GET /backends (useBackends).

export const BACKEND_NAMES: BackendName[] = ['api', 'gguf', 'transformers']

export const BACKENDS: Record<BackendName, { label: string }> = {
  api: { label: 'API' },
  gguf: { label: 'GGUF' },
  transformers: { label: 'Transformers' },
}

export const STRUCTURED_OUTPUT: Record<StructuredOutputMode, { guaranteed: boolean; explanation: string }> = {
  prompt_retry: {
    guaranteed: false,
    explanation:
      'This backend can’t enforce a schema, so the reply is parsed and retried with the error fed back. Usually valid, not guaranteed.',
  },
  grammar: {
    guaranteed: true,
    explanation: 'llama.cpp compiles this schema into a GBNF grammar, so the reply is guaranteed to parse.',
  },
  guided: {
    guaranteed: true,
    explanation:
      'Guided generation (outlines) restricts tokens to the schema, so the reply is guaranteed to parse.',
  },
}

interface ChipLook {
  label: string
  tone: ChipTone
}

// While GET /backends hasn't answered (or failed), capability chips render neutral
// rather than guessing.
const UNKNOWN: ChipLook = { label: '…', tone: 'idle' }

export function structuredOutputChip(mode: StructuredOutputMode | undefined): ChipLook {
  if (mode === undefined) return UNKNOWN
  return STRUCTURED_OUTPUT[mode].guaranteed ? { label: 'guaranteed', tone: 'fit' } : { label: 'best-effort', tone: 'tight' }
}

export function toolCallingChip(native: boolean | undefined): ChipLook {
  if (native === undefined) return UNKNOWN
  return native ? { label: 'native', tone: 'fit' } : { label: 'fallback', tone: 'tight' }
}
