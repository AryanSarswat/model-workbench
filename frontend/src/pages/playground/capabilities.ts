import type { BackendName } from '../../api/types'

// gguf and transformers report native_tool_calling=True (llama_cpp_backend.py,
// transformers_backend.py); the api backend runs the prompt+retry fallback loop
// (hf_api_backend.py) and reports False. The Playground design mockup has this
// backwards -- this is the corrected mapping (see AGENTS brief for this screen).
export const NATIVE_TOOL_CALLING: Record<BackendName, boolean> = {
  api: false,
  gguf: true,
  transformers: true,
}
