import { describe, expect, it } from 'vitest'
import type { DownloadedModelRecord } from '../../api/types'
import { backendDisplayLabel, ggufModelOptions, pickPrefilledModelId, shortModelName } from './modelOptions'

function ggufRecord(overrides: Partial<DownloadedModelRecord>): DownloadedModelRecord {
  return {
    id: 1,
    repo_id: 'Qwen/Qwen3-14B',
    backend: 'gguf',
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
  it('uses the bare repo_id when only one quant of that repo is downloaded', () => {
    const [option] = ggufModelOptions([ggufRecord({})])
    expect(option.modelId).toBe('Qwen/Qwen3-14B')
  })

  it('uses "repo_id:quant" when multiple quants of the same repo are downloaded', () => {
    const [a, b] = ggufModelOptions([ggufRecord({ id: 1, quant: 'Q4_K_M.gguf' }), ggufRecord({ id: 2, quant: 'Q8_0.gguf' })])
    expect(a.modelId).toBe('Qwen/Qwen3-14B:Q4_K_M.gguf')
    expect(b.modelId).toBe('Qwen/Qwen3-14B:Q8_0.gguf')
  })

  it('keeps repos with a single quant each bare, even when other repos are ambiguous', () => {
    const options = ggufModelOptions([
      ggufRecord({ id: 1, repo_id: 'a/repo', quant: 'q1.gguf' }),
      ggufRecord({ id: 2, repo_id: 'b/repo', quant: 'q1.gguf' }),
      ggufRecord({ id: 3, repo_id: 'b/repo', quant: 'q2.gguf' }),
    ])
    expect(options[0].modelId).toBe('a/repo')
    expect(options[1].modelId).toBe('b/repo:q1.gguf')
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
