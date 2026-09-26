import { describe, expect, it } from 'vitest'
import type { DownloadedModelRecord } from '../../api/types'
import { buildRunRequest, modelIdSuggestions } from './runForm'

describe('buildRunRequest', () => {
  it('posts the trimmed model id, chosen backend, and null for unset optional fields', () => {
    expect(buildRunRequest({ modelId: '  Qwen/Qwen3-14B  ', backend: 'gguf', category: '', judgeModelId: '' })).toEqual({
      model_id: 'Qwen/Qwen3-14B',
      backend: 'gguf',
      category: null,
      judge_model_id: null,
    })
  })

  it('carries a chosen category and judge model id through', () => {
    expect(
      buildRunRequest({ modelId: 'google/gemma-3-12b-it', backend: 'api', category: 'coding', judgeModelId: ' gemma-3-12b-it ' }),
    ).toEqual({
      model_id: 'google/gemma-3-12b-it',
      backend: 'api',
      category: 'coding',
      judge_model_id: 'gemma-3-12b-it',
    })
  })
})

function downloaded(overrides: Partial<DownloadedModelRecord> & Pick<DownloadedModelRecord, 'id' | 'repo_id' | 'backend'>): DownloadedModelRecord {
  return {
    quant: null,
    local_path: '/models/x',
    size_bytes: 0,
    downloaded_at: '2026-01-01T00:00:00Z',
    last_used_at: null,
    ...overrides,
  }
}

describe('modelIdSuggestions', () => {
  const reportRows = [
    { model_id: 'google/gemma-3-12b-it', backend: 'api' as const },
    { model_id: 'Qwen/Qwen3-14B', backend: 'gguf' as const }, // wrong backend for the 'api' case below
  ]

  it('api suggests report model ids for the api backend only, ignoring downloaded repos', () => {
    const records = [downloaded({ id: 1, repo_id: 'Qwen/Qwen3-14B', backend: 'gguf' })]
    expect(modelIdSuggestions('api', records, reportRows)).toEqual(['google/gemma-3-12b-it'])
  })

  it('transformers suggests downloaded repo ids for that backend only', () => {
    const records = [
      downloaded({ id: 1, repo_id: 'microsoft/Phi-4-mini-instruct', backend: 'transformers' }),
      downloaded({ id: 2, repo_id: 'Qwen/Qwen3-14B', backend: 'gguf' }),
    ]
    expect(modelIdSuggestions('transformers', records, [])).toEqual(['microsoft/Phi-4-mini-instruct'])
  })

  it('gguf suggests a bare repo id when only one quant is downloaded', () => {
    const records = [downloaded({ id: 1, repo_id: 'Qwen/Qwen3-14B', backend: 'gguf', quant: 'Q4_K_M.gguf' })]
    expect(modelIdSuggestions('gguf', records, [])).toEqual(['Qwen/Qwen3-14B'])
  })

  it('gguf suggests "repo_id:quant" for each quant when several are downloaded', () => {
    const records = [
      downloaded({ id: 1, repo_id: 'Qwen/Qwen3-14B', backend: 'gguf', quant: 'Q4_K_M.gguf' }),
      downloaded({ id: 2, repo_id: 'Qwen/Qwen3-14B', backend: 'gguf', quant: 'Q8_0.gguf' }),
    ]
    expect(modelIdSuggestions('gguf', records, [])).toEqual(['Qwen/Qwen3-14B:Q4_K_M.gguf', 'Qwen/Qwen3-14B:Q8_0.gguf'])
  })
})
