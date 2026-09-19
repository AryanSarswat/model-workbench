# model-workbench

A personal workbench for staying current with trending Hugging Face models: discover them,
run them locally (downloaded) or via the HF Inference API, chat with them, probe structured
output and tool-calling, and evaluate them against your own private, categorized test-case
dataset.

**Status:** early development — backend first, frontend to follow.

## Why

Hugging Face ships new trending models constantly. This tool answers one question quickly:
*is this new model actually good for what I need it for?* — by running your own test cases
against it, locally or via the API, and comparing the results (accuracy, structured-output
reliability, tool-calling reliability, speed, cost) against models you've already tried.

## How it works (high level)

- **Discover** trending or newly-released text-generation models from the HF Hub.
- **Run** a model either fully locally (GGUF via llama.cpp, or transformers as a fallback
  for models without a GGUF build) or remotely via the HF Inference API — same chat
  interface either way.
- **Chat**, optionally with a JSON Schema for structured output and/or a set of tools the
  model can call.
- **Evaluate** a model against your own test-case dataset — organized by category
  (`coding`, `general`, `world_understanding`, `personalization`, ...), scored by manual
  review, automated assertions, and/or LLM-as-judge.

Full architecture: [docs/architecture.md](docs/architecture.md). Setup/run/test: [docs/usage.md](docs/usage.md).

## Your test-case dataset is private

Your real test cases live in `data/test_cases/` and are gitignored — they never leave your
machine. `data/test_cases.template.json` ships in this repo so you can see the schema and
adopt the same workflow with your own cases.

## Status

Backend is being built first, end-to-end, before the frontend. See the design doc for the
full architecture and phasing.

## License

MIT — see [LICENSE](LICENSE).
