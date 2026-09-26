import { describe, expect, it } from 'vitest'
import type { TestCase } from '../../api/types'
import { caseToForm, duplicateForm, emptyForm, formToCase } from './testCaseForm'

describe('formToCase', () => {
  it('rejects an id with characters outside the backend-allowed set', () => {
    const form = { ...emptyForm('coding'), id: 'has a space', messages: [{ role: 'user' as const, content: 'hi' }] }
    const { testCase, errors } = formToCase(form)
    expect(testCase).toBeNull()
    expect(errors).toContain('ID may only contain letters, digits, dot, underscore and dash.')
  })

  it('drops empty optional fields instead of sending empty strings', () => {
    const form = {
      ...emptyForm('coding'),
      id: 'coding-001',
      messages: [{ role: 'user' as const, content: 'hi' }],
      systemPrompt: '   ',
      judgeCriteria: '',
      outputSchema: '',
      tags: '',
    }
    const { testCase, errors } = formToCase(form)
    expect(errors).toEqual([])
    expect(testCase).toMatchObject({
      system_prompt: null,
      judge: null,
      output_schema: null,
      expected_tools: null,
      tags: [],
    })
  })

  it('maps each assertion type argument to its backend field', () => {
    const form = {
      ...emptyForm('coding'),
      id: 'coding-002',
      messages: [{ role: 'user' as const, content: 'hi' }],
      assertions: [
        { type: 'contains' as const, argument: 'expected text' },
        { type: 'regex' as const, argument: '^def' },
        { type: 'tool_called' as const, argument: 'calculator' },
        { type: 'schema_valid' as const, argument: 'ignored for this type' },
      ],
    }
    const { testCase, errors } = formToCase(form)
    expect(errors).toEqual([])
    expect(testCase?.assertions).toEqual([
      { type: 'contains', value: 'expected text', pattern: undefined, name: undefined },
      { type: 'regex', pattern: '^def', value: undefined, name: undefined },
      { type: 'tool_called', name: 'calculator', value: undefined, pattern: undefined },
      { type: 'schema_valid' },
    ])
  })

  it('rejects an output schema that is not a JSON object', () => {
    const form = {
      ...emptyForm('coding'),
      id: 'coding-003',
      messages: [{ role: 'user' as const, content: 'hi' }],
      outputSchema: '[1, 2, 3]',
    }
    const { testCase, errors } = formToCase(form)
    expect(testCase).toBeNull()
    expect(errors).toContain('Output schema must be a JSON object.')
  })

  it('rejects a case with no non-empty messages', () => {
    const form = { ...emptyForm('coding'), id: 'coding-004', messages: [{ role: 'user' as const, content: '   ' }] }
    const { testCase, errors } = formToCase(form)
    expect(testCase).toBeNull()
    expect(errors).toContain('At least one message with content is required.')
  })

  // A blank value here would otherwise save as null and always fail at eval time
  // (backend/app/evals/assertions.py requires it for these three types).
  it.each([
    ['contains', 'a value'],
    ['regex', 'a pattern'],
    ['tool_called', 'a tool name'],
  ] as const)('rejects a blank argument for a %s assertion', (type, label) => {
    const form = {
      ...emptyForm('coding'),
      id: 'coding-005',
      messages: [{ role: 'user' as const, content: 'hi' }],
      assertions: [{ type, argument: '   ' }],
    }
    const { testCase, errors } = formToCase(form)
    expect(testCase).toBeNull()
    expect(errors).toContain(`Assertion 1 (${type}) requires ${label}.`)
  })

  it('accepts assertions with no argument requirement left blank', () => {
    const form = {
      ...emptyForm('coding'),
      id: 'coding-006',
      messages: [{ role: 'user' as const, content: 'hi' }],
      assertions: [{ type: 'schema_valid' as const, argument: '' }],
    }
    const { testCase, errors } = formToCase(form)
    expect(errors).toEqual([])
    expect(testCase?.assertions).toEqual([{ type: 'schema_valid' }])
  })
})

describe('caseToForm / duplicateForm round trip', () => {
  const testCase: TestCase = {
    id: 'coding-007',
    category: 'coding',
    messages: [{ role: 'user', content: 'Write fib(n).' }],
    system_prompt: null,
    output_schema: { type: 'object' },
    expected_tools: ['calculator'],
    assertions: [{ type: 'contains', value: 'def fib' }],
    judge: { criteria: 'Correct and iterative.' },
    tags: ['python', 'basics'],
  }

  it('round-trips a case through the form and back unchanged', () => {
    const form = caseToForm(testCase)
    const { testCase: rebuilt, errors } = formToCase(form)
    expect(errors).toEqual([])
    expect(rebuilt).toEqual(testCase)
  })

  it('prefills a duplicate with a -copy id and keeps the rest of the draft', () => {
    const dup = duplicateForm(caseToForm(testCase))
    expect(dup.id).toBe('coding-007-copy')
    expect(dup.category).toBe('coding')
    expect(dup.tags).toBe('python, basics')
  })
})
