import { describe, expect, it } from 'vitest'
import type { DownloadJob, DownloadedModelRecord, EvalReportRow } from '../../api/types'
import {
  bestEvalBackend,
  findActiveGgufJob,
  findActiveSnapshotJob,
  findDownloadedGguf,
  findDownloadedSnapshot,
  optionBackend,
  playgroundLink,
} from './modelHelpers'

const downloaded: DownloadedModelRecord[] = [
  {
    id: 1,
    repo_id: 'Qwen/Qwen3-14B',
    backend: 'gguf',
    quant: 'Qwen3-14B-Q4_K_M.gguf',
    local_path: '/models/Qwen3-14B-Q4_K_M.gguf',
    size_bytes: 9_000_000_000,
    downloaded_at: '2026-01-01T00:00:00Z',
    last_used_at: null,
  },
]

const jobs: DownloadJob[] = [
  {
    id: 7,
    repo_id: 'Qwen/Qwen3-14B',
    kind: 'gguf',
    filename: 'Qwen3-14B-Q5_K_M.gguf',
    current_file: null,
    status: 'downloading',
    percent: 62,
    detail: '',
    error: null,
    downloaded_model_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

describe('optionBackend', () => {
  it('reads gguf from a .gguf filename and transformers otherwise', () => {
    expect(optionBackend('Qwen3-14B-Q4_K_M.gguf')).toBe('gguf')
    expect(optionBackend('transformers (BF16)')).toBe('transformers')
  })
})

describe('findDownloadedGguf / findDownloadedSnapshot', () => {
  it('matches a downloaded record by repo and quant, and ignores other models', () => {
    expect(findDownloadedGguf(downloaded, 'Qwen/Qwen3-14B', 'Qwen3-14B-Q4_K_M.gguf')).toBe(downloaded[0])
    expect(findDownloadedGguf(downloaded, 'Qwen/Qwen3-14B', 'Qwen3-14B-Q3_K_M.gguf')).toBeUndefined()
    expect(findDownloadedGguf(downloaded, 'other/model', 'Qwen3-14B-Q4_K_M.gguf')).toBeUndefined()
    expect(findDownloadedSnapshot(downloaded, 'Qwen/Qwen3-14B')).toBeUndefined()
  })
})

describe('findActiveGgufJob / findActiveSnapshotJob', () => {
  it('matches an active job by repo, kind and filename', () => {
    expect(findActiveGgufJob(jobs, 'Qwen/Qwen3-14B', 'Qwen3-14B-Q5_K_M.gguf')).toBe(jobs[0])
    expect(findActiveGgufJob(jobs, 'Qwen/Qwen3-14B', 'Qwen3-14B-Q6_K.gguf')).toBeUndefined()
    expect(findActiveSnapshotJob(jobs, 'Qwen/Qwen3-14B')).toBeUndefined()
  })
})

describe('playgroundLink', () => {
  it('prefers an on-disk gguf quant over a snapshot or the API', () => {
    expect(playgroundLink('Qwen/Qwen3-14B', downloaded)).toBe(
      '/playground?model=Qwen%2FQwen3-14B&backend=gguf&quant=Qwen3-14B-Q4_K_M.gguf',
    )
  })

  it('falls back to a transformers snapshot, then to the api backend', () => {
    const snapshot: DownloadedModelRecord[] = [{ ...downloaded[0], backend: 'transformers', quant: null }]
    expect(playgroundLink('Qwen/Qwen3-14B', snapshot)).toBe('/playground?model=Qwen%2FQwen3-14B&backend=transformers')
    expect(playgroundLink('Qwen/Qwen3-14B', [])).toBe('/playground?model=Qwen%2FQwen3-14B&backend=api')
  })
})

describe('bestEvalBackend', () => {
  it('picks the backend with the most evaluated cases', () => {
    const rows: EvalReportRow[] = [
      {
        model_id: 'm',
        backend: 'api',
        category: 'coding',
        cases: 5,
        passed: 3,
        pass_rate: 0.6,
        avg_tokens_per_sec: null,
        avg_ttft_ms: null,
        structured_output_reliability: null,
        tool_calling_reliability: null,
        latest_run_id: 1,
      },
      {
        model_id: 'm',
        backend: 'gguf',
        category: 'coding',
        cases: 10,
        passed: 8,
        pass_rate: 0.8,
        avg_tokens_per_sec: null,
        avg_ttft_ms: null,
        structured_output_reliability: null,
        tool_calling_reliability: null,
        latest_run_id: 2,
      },
    ]
    expect(bestEvalBackend(rows)).toBe('gguf')
    expect(bestEvalBackend([])).toBeNull()
  })
})
