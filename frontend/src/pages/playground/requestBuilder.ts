import type { BackendName, ChatMessage, ChatRequest } from '../../api/types'

export interface BuildChatRequestArgs {
  modelId: string
  backend: BackendName
  messages: ChatMessage[] // full user/assistant history, in order, ending with the new user turn
  systemPrompt: string
  tools: string[] // selected tool names
  outputSchema: Record<string, unknown> | null
}

// The system prompt (when non-empty) goes first as a system-role message; tools and
// output_schema are only sent when the caller actually enabled them (see ChatRequest).
export function buildChatRequest({ modelId, backend, messages, systemPrompt, tools, outputSchema }: BuildChatRequestArgs): ChatRequest {
  const trimmedSystemPrompt = systemPrompt.trim()
  const fullMessages: ChatMessage[] = trimmedSystemPrompt
    ? [{ role: 'system', content: trimmedSystemPrompt }, ...messages]
    : messages
  return {
    model_id: modelId,
    messages: fullMessages,
    backend,
    tools: tools.length > 0 ? tools : null,
    output_schema: outputSchema,
  }
}

export type SchemaParseResult = { ok: true; schema: Record<string, unknown> } | { ok: false; error: string }

// Validity here is only "is this parseable JSON that looks like a schema object" --
// the backend is the source of truth for whether it's a *valid JSON Schema* (a 400
// pre-stream when it isn't). We don't implement a JSON-Schema validator client-side.
export function parseSchemaJson(text: string): SchemaParseResult {
  try {
    const parsed: unknown = JSON.parse(text)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { ok: false, error: 'Schema must be a JSON object.' }
    }
    return { ok: true, schema: parsed as Record<string, unknown> }
  } catch (err) {
    const detail = err instanceof Error ? err.message : 'Invalid JSON.'
    return { ok: false, error: `Invalid JSON: ${detail}` }
  }
}
