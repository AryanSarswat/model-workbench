import { describe, expect, it } from 'vitest'
import type { DownloadedModelRecord } from '../../api/types'
import { formatChip } from './libraryFormat'

function gguf(repo_id: string, quant: string): DownloadedModelRecord {
  return {
    id: 1,
    repo_id,
    backend: 'gguf',
    model_id: repo_id,
    quant,
    local_path: `/models/${quant}`,
    size_bytes: 1,
    downloaded_at: '2026-09-20T00:00:00Z',
    last_used_at: null,
    unsupported_reason: null,
  }
}

describe('formatChip', () => {
  // The chip column is narrow, so the model name the row already shows is dropped
  // from the quant filename -- however the repo and file differ in case or suffix.
  it('keeps only the quant when the file repeats the repo name', () => {
    expect(formatChip(gguf('Qwen/Qwen2.5-0.5B-Instruct-GGUF', 'qwen2.5-0.5b-instruct-q4_k_m.gguf'))).toBe(
      'GGUF · q4_k_m',
    )
    expect(formatChip(gguf('prism-ml/Ternary-Bonsai-2-27B-gguf', 'Ternary-Bonsai-2-27B-PQ2_0.gguf'))).toBe(
      'GGUF · PQ2_0',
    )
  })

  it('keeps the whole filename when it does not repeat the repo name', () => {
    expect(formatChip(gguf('someone/Other-GGUF', 'model-Q8_0.gguf'))).toBe('GGUF · model-Q8_0')
  })
})
