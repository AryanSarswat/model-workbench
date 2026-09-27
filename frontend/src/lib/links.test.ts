import { describe, expect, it } from 'vitest'
import { playgroundPath } from './links'

describe('playgroundPath', () => {
  it('encodes the model id and only carries a quant for GGUF', () => {
    expect(playgroundPath({ model: 'Qwen/Qwen3-14B', backend: 'gguf', quant: 'Qwen3-14B-Q4_K_M.gguf' })).toBe(
      '/playground?model=Qwen%2FQwen3-14B&backend=gguf&quant=Qwen3-14B-Q4_K_M.gguf',
    )
    expect(playgroundPath({ model: 'Qwen/Qwen3-14B', backend: 'transformers', quant: 'ignored.gguf' })).toBe(
      '/playground?model=Qwen%2FQwen3-14B&backend=transformers',
    )
  })
})
