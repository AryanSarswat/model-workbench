import { describe, expect, it } from 'vitest'
import { buildRunRequest, modelIdSuggestions, sortedCategories } from './runForm'

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

describe('sortedCategories', () => {
  it('de-duplicates and sorts', () => {
    expect(sortedCategories(['general', 'coding', 'general', 'coding'])).toEqual(['coding', 'general'])
  })
})

describe('modelIdSuggestions', () => {
  it('merges downloaded and reported model ids without duplicates', () => {
    expect(modelIdSuggestions(['a', 'b'], ['b', 'c'])).toEqual(['a', 'b', 'c'])
  })
})
