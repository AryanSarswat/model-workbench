import { describe, expect, it } from 'vitest'
import type { DownloadedModelRecord } from '../../api/types'
import { backendDisplayLabel, ggufModelOptions, pickPrefilledModelId, shortModelName, transformersModelOptions } from './modelOptions'

function ggufRecord(overrides: Partial<DownloadedModelRecord>): DownloadedModelRecord {
  return {
    id: 1,
    repo_id: 'Qwen/Qwen3-14B',
    backend: 'gguf',
    model_id: 'Qwen/Qwen3-14B',
    quant: 'Q4_K_M.gguf',
    local_path: '/models/x',
    size_bytes: 1,
    downloaded_at: '2024-01-01T00:00:00Z',
    last_used_at: null,
    unsupported_reason: null,
    ...overrides,
  }
}

describe('ggufModelOptions', () => {
  it("sends the backend's model_id, labelled by repo alone when it is a bare repo_id", () => {
    const [option] = ggufModelOptions([ggufRecord({})])
    expect(option).toMatchObject({ modelId: 'Qwen/Qwen3-14B', label: 'Qwen/Qwen3-14B' })
  })

  it('names the quant in the label when the backend picked "repo_id:quant"', () => {
    const [option] = ggufModelOptions([ggufRecord({ model_id: 'Qwen/Qwen3-14B:Q8_0.gguf', quant: 'Q8_0.gguf' })])
    expect(option).toMatchObject({ modelId: 'Qwen/Qwen3-14B:Q8_0.gguf', label: 'Qwen/Qwen3-14B (Q8_0.gguf)' })
  })
})

describe('transformersModelOptions', () => {
  it('lists repeated downloads of one repo once', () => {
    const record = ggufRecord({ backend: 'transformers', quant: null })
    expect(transformersModelOptions([record, { ...record, id: 2 }]).map((o) => o.modelId)).toEqual(['Qwen/Qwen3-14B'])
  })
})

describe('pickPrefilledModelId', () => {
  const options = [
    { modelId: 'Qwen/Qwen3-14B:Q4_K_M.gguf', label: 'Qwen/Qwen3-14B (Q4_K_M.gguf)', unloadable: null },
    { modelId: 'other/repo', label: 'other/repo', unloadable: null },
  ]

  it('matches an exact model+quant combination', () => {
    expect(pickPrefilledModelId(options, 'Qwen/Qwen3-14B', 'Q4_K_M.gguf')).toBe('Qwen/Qwen3-14B:Q4_K_M.gguf')
  })

  it('falls back to the first option when nothing matches', () => {
    expect(pickPrefilledModelId(options, 'unknown/repo', null)).toBe('Qwen/Qwen3-14B:Q4_K_M.gguf')
  })
})

describe('display labels', () => {
  it('shortens a repo id to its final path segment', () => {
    expect(shortModelName('Qwen/Qwen3-14B:Q4_K_M.gguf')).toBe('Qwen3-14B')
  })

  it('labels the gguf backend with its quant file when present', () => {
    expect(backendDisplayLabel('gguf', 'Qwen/Qwen3-14B:Q4_K_M.gguf')).toBe('gguf Q4_K_M.gguf')
    expect(backendDisplayLabel('gguf', 'Qwen/Qwen3-14B')).toBe('gguf')
  })
})
