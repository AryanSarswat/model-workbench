// Pure conversion between the case editor's form state and the API's TestCase shape.
// Kept dependency-free (no React) so it's easy to unit test.
import type { Assertion, AssertionType, ChatMessage, TestCase } from '../../api/types'

const ID_PATTERN = /^[A-Za-z0-9._-]+$/

export const ASSERTION_TYPES: AssertionType[] = [
  'schema_valid',
  'contains',
  'regex',
  'tool_called',
  'structured_output_first_try',
  'native_tool_calling',
  'json_parse_success',
]

// Assertions with no argument (their input is disabled with "no value needed").
export function assertionNeedsArgument(type: AssertionType): boolean {
  return type === 'contains' || type === 'regex' || type === 'tool_called'
}

export function assertionArgPlaceholder(type: AssertionType): string {
  switch (type) {
    case 'contains':
      return 'substring to find in the response'
    case 'regex':
      return 'pattern'
    case 'tool_called':
      return 'tool name'
    default:
      return 'no value needed'
  }
}

// Short label for validation messages ("Assertion 2 (contains) requires a value.").
function assertionArgLabel(type: AssertionType): string {
  switch (type) {
    case 'contains':
      return 'a value'
    case 'regex':
      return 'a pattern'
    case 'tool_called':
      return 'a tool name'
    default:
      return 'a value'
  }
}

export interface MessageForm {
  role: ChatMessage['role']
  content: string
}

export interface AssertionForm {
  type: AssertionType
  argument: string
}

export interface CaseFormState {
  id: string
  category: string
  tags: string // comma-separated
  messages: MessageForm[]
  systemPrompt: string
  judgeCriteria: string
  outputSchema: string // raw JSON text, empty allowed
  expectedTools: string[]
  assertions: AssertionForm[]
}

export function emptyForm(category = ''): CaseFormState {
  return {
    id: '',
    category,
    tags: '',
    messages: [{ role: 'user', content: '' }],
    systemPrompt: '',
    judgeCriteria: '',
    outputSchema: '',
    expectedTools: [],
    assertions: [],
  }
}

export function caseToForm(testCase: TestCase): CaseFormState {
  return {
    id: testCase.id,
    category: testCase.category,
    tags: (testCase.tags ?? []).join(', '),
    messages: testCase.messages.map((m) => ({ role: m.role, content: m.content })),
    systemPrompt: testCase.system_prompt ?? '',
    judgeCriteria: testCase.judge?.criteria ?? '',
    outputSchema: testCase.output_schema ? JSON.stringify(testCase.output_schema, null, 2) : '',
    expectedTools: testCase.expected_tools ?? [],
    assertions: (testCase.assertions ?? []).map((a) => ({
      type: a.type,
      argument: a.value ?? a.pattern ?? a.name ?? '',
    })),
  }
}

// Prefills a new, unsaved draft from an existing case with a "-copy" id.
export function duplicateForm(form: CaseFormState): CaseFormState {
  return { ...form, id: form.id ? `${form.id}-copy` : '' }
}

export interface FormToCaseResult {
  testCase: TestCase | null
  errors: string[]
}

// Validates and converts form state to a TestCase, or returns validation errors.
// Empty optional fields are dropped (null/omitted), never sent as "".
export function formToCase(form: CaseFormState): FormToCaseResult {
  const errors: string[] = []

  const id = form.id.trim()
  if (!id) errors.push('ID is required.')
  else if (!ID_PATTERN.test(id)) errors.push('ID may only contain letters, digits, dot, underscore and dash.')

  const category = form.category.trim()
  if (!category) errors.push('Category is required.')

  const messages: ChatMessage[] = form.messages
    .map((m) => ({ role: m.role, content: m.content.trim() }))
    .filter((m) => m.content.length > 0)
  if (messages.length === 0) errors.push('At least one message with content is required.')

  let outputSchema: Record<string, unknown> | null = null
  const schemaText = form.outputSchema.trim()
  if (schemaText) {
    try {
      const parsed: unknown = JSON.parse(schemaText)
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        errors.push('Output schema must be a JSON object.')
      } else {
        outputSchema = parsed as Record<string, unknown>
      }
    } catch {
      errors.push('Output schema is not valid JSON.')
    }
  }

  // A blank value here always fails the corresponding assertion at eval time
  // (backend/app/evals/assertions.py), so treat it as a validation error rather than
  // silently saving a null.
  form.assertions.forEach((a, index) => {
    if (assertionNeedsArgument(a.type) && !a.argument.trim()) {
      errors.push(`Assertion ${index + 1} (${a.type}) requires ${assertionArgLabel(a.type)}.`)
    }
  })

  if (errors.length > 0) return { testCase: null, errors }

  const tags = form.tags
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)

  const assertions: Assertion[] = form.assertions.map((a) => {
    const argument = a.argument.trim()
    switch (a.type) {
      case 'contains':
        return { type: a.type, value: argument }
      case 'regex':
        return { type: a.type, pattern: argument }
      case 'tool_called':
        return { type: a.type, name: argument }
      default:
        return { type: a.type }
    }
  })

  const testCase: TestCase = {
    id,
    category,
    messages,
    system_prompt: form.systemPrompt.trim() || null,
    output_schema: outputSchema,
    expected_tools: form.expectedTools.length > 0 ? form.expectedTools : null,
    assertions,
    judge: form.judgeCriteria.trim() ? { criteria: form.judgeCriteria.trim() } : null,
    tags,
  }
  return { testCase, errors: [] }
}

// Badges shown on a case's row in the list.
export function caseBadges(testCase: TestCase): string[] {
  const badges: string[] = []
  if (testCase.output_schema) badges.push('schema')
  if (testCase.judge) badges.push('judge')
  if (testCase.expected_tools && testCase.expected_tools.length > 0) badges.push('tools')
  const checks = testCase.assertions?.length ?? 0
  if (checks > 0) badges.push(`${checks} check${checks === 1 ? '' : 's'}`)
  return badges
}

// First user message's content, for the list preview.
export function firstUserMessage(testCase: TestCase): string {
  return testCase.messages.find((m) => m.role === 'user')?.content ?? testCase.messages[0]?.content ?? ''
}

// Whether a case matches free-text search across id, prompt, tags and assertion types.
export function matchesSearch(testCase: TestCase, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  if (testCase.id.toLowerCase().includes(q)) return true
  if (firstUserMessage(testCase).toLowerCase().includes(q)) return true
  if ((testCase.tags ?? []).some((tag) => tag.toLowerCase().includes(q))) return true
  if ((testCase.assertions ?? []).some((a) => a.type.toLowerCase().includes(q))) return true
  return false
}
