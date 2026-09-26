import type { BackendName } from '../api/types'

export interface BackendInfo {
  label: string
  structuredOutputMode: 'grammar' | 'guided' | 'prompt_retry'
  guarantee: 'guaranteed' | 'best-effort'
  explanation: string // one sentence on how structured output is enforced
}

export const BACKEND_NAMES: BackendName[] = ['api', 'gguf', 'transformers']

export const BACKENDS: Record<BackendName, BackendInfo> = {
  api: {
    label: 'API',
    structuredOutputMode: 'prompt_retry',
    guarantee: 'best-effort',
    explanation:
      'The API can’t enforce a schema, so the reply is parsed and retried with the error fed back. Usually valid, not guaranteed.',
  },
  gguf: {
    label: 'GGUF',
    structuredOutputMode: 'grammar',
    guarantee: 'guaranteed',
    explanation: 'llama.cpp compiles this schema into a GBNF grammar, so the reply is guaranteed to parse.',
  },
  transformers: {
    label: 'Transformers',
    structuredOutputMode: 'guided',
    guarantee: 'guaranteed',
    explanation:
      'Guided generation (outlines) restricts tokens to the schema, so the reply is guaranteed to parse.',
  },
}
