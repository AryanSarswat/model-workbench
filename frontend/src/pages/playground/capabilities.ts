import type { BackendName } from '../../api/types'

// Mirrors each backend's capabilities(): LlamaCppBackend and TransformersBackend
// report native_tool_calling=True (llama_cpp_backend.py, transformers_backend.py);
// HFInferenceAPIBackend runs the prompt+retry fallback loop and reports False
// (hf_api_backend.py). The Playground design mockup has the tools chip backwards.
export const NATIVE_TOOL_CALLING: Record<BackendName, boolean> = {
  api: false,
  gguf: true,
  transformers: true,
}
