import { describe, expect, it } from 'vitest'
import { buildChatRequest, parseSchemaJson } from './requestBuilder'

describe('buildChatRequest', () => {
  it('puts a non-empty system prompt first', () => {
    const request = buildChatRequest({
      modelId: 'Qwen/Qwen3-14B',
      backend: 'api',
      messages: [{ role: 'user', content: 'hi' }],
      systemPrompt: 'Be concise.',
      tools: [],
      outputSchema: null,
    })

    expect(request.messages).toEqual([
      { role: 'system', content: 'Be concise.' },
      { role: 'user', content: 'hi' },
    ])
  })

  it('omits the system message when the prompt is blank', () => {
    const request = buildChatRequest({
      modelId: 'Qwen/Qwen3-14B',
      backend: 'api',
      messages: [{ role: 'user', content: 'hi' }],
      systemPrompt: '   ',
      tools: [],
      outputSchema: null,
    })

    expect(request.messages).toEqual([{ role: 'user', content: 'hi' }])
  })

  it('sends tools only when at least one is selected', () => {
    const withTools = buildChatRequest({ modelId: 'm', backend: 'gguf', messages: [], systemPrompt: '', tools: ['calculator'], outputSchema: null })
    expect(withTools.tools).toEqual(['calculator'])

    const withoutTools = buildChatRequest({ modelId: 'm', backend: 'gguf', messages: [], systemPrompt: '', tools: [], outputSchema: null })
    expect(withoutTools.tools).toBeNull()
  })

  it('passes the output schema through only when enabled', () => {
    const schema = { type: 'object' }
    const enabled = buildChatRequest({ modelId: 'm', backend: 'gguf', messages: [], systemPrompt: '', tools: [], outputSchema: schema })
    expect(enabled.output_schema).toBe(schema)

    const disabled = buildChatRequest({ modelId: 'm', backend: 'gguf', messages: [], systemPrompt: '', tools: [], outputSchema: null })
    expect(disabled.output_schema).toBeNull()
  })
})

describe('parseSchemaJson', () => {
  it('parses a valid JSON object', () => {
    expect(parseSchemaJson('{"type": "object"}')).toEqual({ ok: true, schema: { type: 'object' } })
  })

  it('rejects invalid JSON, blocking send', () => {
    const result = parseSchemaJson('{not json')
    expect(result.ok).toBe(false)
  })

  it('rejects valid JSON that is not an object', () => {
    const result = parseSchemaJson('[1, 2, 3]')
    expect(result.ok).toBe(false)
  })
})
