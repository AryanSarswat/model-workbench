import type { BackendName } from '../../api/types'

// Mirrors each backend's capabilities(): only LlamaCppBackend reports
// native_tool_calling=True (llama_cpp_backend.py); TransformersBackend and
// HFInferenceAPIBackend run the prompt+retry fallback loop and report False
// (transformers_backend.py, hf_api_backend.py).
export const NATIVE_TOOL_CALLING: Record<BackendName, boolean> = {
  api: false,
  gguf: true,
  transformers: false,
}
