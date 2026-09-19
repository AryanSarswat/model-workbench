# model-workbench — Backend Design

**Date:** 2026-09-19
**Status:** Approved for implementation (backend only — frontend deferred to a follow-on spec)

## 1. Purpose

A personal tool for staying current with trending/new Hugging Face models: discover them,
run them either locally (downloaded) or via the HF Inference API, chat with them, probe their
structured-output and tool-calling capabilities, and evaluate them against a private,
categorized set of test cases the user maintains over time.

Single web app, Python backend + React frontend, public MIT-licensed repo (`model-workbench`).
The private test-case dataset never leaves the user's machine; a template ships in the repo so
others can adopt the same workflow with their own cases.

## 2. Phasing

This is a large idea (multiple model modalities, dual inference paths, an eval system, an
extensible tool framework). It is being built in phases to avoid a sprawling half-working v1:

- **Phase 1 (this spec): backend only, text-generation/chat models only.** Every subsystem
  below (discovery, download, inference abstraction, structured output, tools, eval engine)
  is implemented and testable via HTTP/SSE without a UI.
- **Phase 2 (future spec): frontend.** A React UI is designed and built against the Phase 1
  API once the backend is proven. Deferred rather than co-designed now because the user
  wants the backend fully solid first.
- **Phase 3+ (future specs, not designed yet): additional modalities** — vision-language,
  audio, image-generation, embeddings — each added as its own inference backend module and
  its own spec, plugging into the same registry/download/eval infrastructure. The
  architecture below is written so a new modality means adding a new `InferenceBackend`
  implementation and a new model-card renderer, not restructuring the app.

**Explicitly out of scope for Phase 1:** any frontend code, Docker packaging (deferred until
a frontend service exists to compose alongside it — Phase 1 runs via a local venv), and
non-text-generation modalities.

## 3. Repository layout

```
model-workbench/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, router registration
│   │   ├── config.py              # settings, hf-api-key storage, hardware detection
│   │   ├── models/                # SQLModel table definitions
│   │   ├── discovery/             # HF Hub trending/recent + model detail + feasibility
│   │   ├── downloads/             # download manager, job tracking, tqdm progress
│   │   ├── inference/
│   │   │   ├── base.py            # InferenceBackend protocol, BackendCapabilities
│   │   │   ├── llama_cpp_backend.py
│   │   │   ├── transformers_backend.py
│   │   │   ├── hf_api_backend.py
│   │   │   ├── structured_output.py  # grammar builders + PromptJsonRetrier
│   │   │   └── tool_loop.py        # tool-call orchestration
│   │   ├── tools/                  # ⚠ THE shared, hot-reloadable tool directory (see §7)
│   │   │   ├── __init__.py         # registry: scan, load, reload
│   │   │   ├── calculator.py       # example tool
│   │   │   └── web_search.py       # example tool
│   │   ├── dataset/                 # test-case CRUD, category filtering
│   │   ├── evals/                   # eval run engine, assertions, judge
│   │   └── api/                     # FastAPI routers (chat, models, tools, dataset, evals, config)
│   ├── tests/
│   ├── pyproject.toml
│   └── .env.example
├── data/                            # gitignored except templates
│   ├── test_cases.template.json
│   └── .gitkeep
├── docs/
├── .gitignore
├── LICENSE                          # MIT
└── README.md
```

## 4. Data model

### 4.1 Test case (private dataset — `data/test_cases/*.json`)

```json
{
  "id": "uuid",
  "category": "coding",
  "messages": [{"role": "user", "content": "..."}],
  "system_prompt": "optional",
  "output_schema": { "...optional JSON Schema..." },
  "expected_tools": ["optional tool names the model should call"],
  "assertions": [
    {"type": "schema_valid"},
    {"type": "contains", "value": "..."},
    {"type": "regex", "pattern": "..."},
    {"type": "tool_called", "name": "calculator"},
    {"type": "structured_output_first_try"},
    {"type": "native_tool_calling"},
    {"type": "json_parse_success"}
  ],
  "judge": {"criteria": "optional rubric text for LLM-as-judge"},
  "tags": ["optional", "free-form"]
}
```

`category` is a free-form string, not a fixed enum — the shipped template suggests
`coding`, `general`, `world_understanding`, `personalization`, but the user can add new
categories without any code change. Every field except `id`, `category`, and `messages` is
optional; a case can be manual-only, assertion-only, judge-only, or any mix.

### 4.2 SQLite tables (`data/workbench.db`, gitignored — SQLModel definitions)

- `chat_sessions`, `chat_messages`
- `downloaded_models` (repo id, backend type, local path, quant, size, last-used)
- `eval_runs` (model_id, backend, dataset snapshot hash, started/finished)
- `eval_results` (run_id, case_id, category, response, assertion results, judge verdict,
  manual verdict, manual notes, metrics JSON)
- `response_metrics` — recorded for **every** chat turn, not just eval runs, so ordinary
  chatting also builds up comparable performance data (tokens/sec, TTFT, latency, cost,
  RAM/VRAM usage)

## 5. Inference engine

### 5.1 Common interface

```python
class InferenceBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...  # supports_grammar, supports_native_tools
    async def stream_chat(
        self, messages, tools=None, output_schema=None
    ) -> AsyncIterator[ChatChunk]: ...
```

Three implementations: `LlamaCppBackend` (GGUF, runs on any hardware via llama-cpp-python),
`TransformersBackend` (fallback for models without a GGUF build; auto-detects MPS/CUDA/CPU),
`HFInferenceAPIBackend` (remote, via `huggingface_hub.InferenceClient`). The API layer
selects one via a `backend: "local" | "api"` request field; callers never touch backend
classes directly.

### 5.2 Structured output

| Backend | Mechanism | Guarantee |
|---|---|---|
| llama.cpp | JSON Schema → GBNF grammar (`LlamaGrammar.from_json_schema`) | Guaranteed valid |
| transformers | `outlines` guided generation | Guaranteed valid |
| HF Inference API | Prompt + parse + retry (via `PromptJsonRetrier`) | Best-effort |

`capabilities()` reports which mode is active so responses can be labeled
"grammar-enforced" vs "best-effort" — this distinction also feeds eval assertions.

### 5.3 Tool calling

1. Tools are Python modules in `backend/app/tools/` (see §7), each exposing a name,
   description, and JSON-schema args.
2. If the model's chat template natively supports a `tools=[...]` argument, use it directly.
3. Otherwise, fall back to `PromptJsonRetrier` with a schema shaped like
   `{tool_call: {name, arguments}} | {reply: string}` — the **same** retry/error-feedback
   loop used for structured-output fallback, not a separate code path.
4. On a tool call, execute the function, append the result as a `tool`-role message, and
   continue generation, up to `max_tool_iterations` (default 5).

Every response records `tool_calling_mode` (`native` / `fallback` / `failed`) and
`structured_output_mode` (`grammar` / `best_effort_ok` / `best_effort_failed`) plus retry
counts — these become first-class eval signals (§6) at no extra implementation cost.

## 6. Eval engine

```
POST /evals/run { model_id, backend, category?, judge_model_id? }
```

Each matching test case is run through the **same** chat path used for regular chat — no
eval-specific inference logic. Recorded automatically per case: the response, structured
output/tool-calling modes and retry counts, and performance metrics. Assertions
(`schema_valid`, `contains`, `regex`, `tool_called`, `structured_output_first_try`,
`native_tool_calling`, `json_parse_success`) run automatically. If a case has
`judge.criteria`, a second call to `judge_model_id` (any registered model, local or remote)
scores the response and stores its verdict + reasoning. Every result also carries a
`manual_verdict`/`manual_notes` pair for hand review, regardless of automated results.
Aggregating `eval_results` by `(model_id, backend, category)` produces the actual
model-comparison report: pass rate, avg tokens/sec, avg cost, tool-calling reliability %,
structured-output reliability %.

## 7. Shared tools directory

`backend/app/tools/` is the single source of truth for available tools — no separate
database table to keep in sync. Each file exposes:

```python
TOOL_SPEC = ToolSpec(name="calculator", description="...", args_schema={...})
async def run(args: dict) -> Any: ...
```

- **Add**: drop a new file in the directory. **Modify**: edit + reload. **Delete**: remove
  the file + reload.
- `POST /tools/reload` rescans without restarting the server, so a new tool can be tested
  immediately.
- Chat/eval requests carry an optional `tool_names: [...]` filter so a tool can be tested
  against one model without exposing it everywhere else, while every model draws from the
  same registry.
- Filesystem-based management only for Phase 1 (no in-app tool source editor) — this is a
  deliberate simplicity choice; an in-app editor would be a meaningfully bigger feature and
  can be revisited if needed.

## 8. Discovery, downloads, and feasibility

- `GET /models/discover?sort=trending|recent&limit=20` — `trending` uses HF's trending
  score; `recent` sorts by `createdAt` descending so brand-new releases surface before
  they've accumulated likes/downloads.
- `GET /models/{id}` — detail, including available GGUF quant files if any.
- `GET /models/{id}/feasibility?quant=...` — estimates memory requirement (GGUF: file size
  + ~20% overhead for KV cache; transformers: param count × bytes-per-dtype) and compares
  against `GET /config/hardware` (detected RAM/VRAM/GPU) to return
  `comfortable | tight | wont_fit` plus a plain-English reason. Advisory, not a hard block.
- `POST /models/{id}/download {quant?, backend}` → job id. Progress is tracked with `tqdm`
  server-side (for terminal visibility when running natively) and mirrored as SSE events of
  the shape `{step, percent, detail}` for the API consumer. Eval runs use the analogous
  `{completed, total, current_case}` shape.
- `GET /models/downloaded`, `DELETE /models/downloaded/{id}`.

## 9. Full API surface

| Area | Endpoints |
|---|---|
| Discovery/downloads | `GET /models/discover`, `GET /models/{id}`, `GET /models/{id}/feasibility`, `POST /models/{id}/download`, `GET /models/downloads/{job_id}`, `GET /models/downloaded`, `DELETE /models/downloaded/{id}` |
| Chat | `POST /chat/stream` (SSE), `GET/DELETE /chat/sessions[/{id}]` |
| Tools | `GET /tools`, `POST /tools/reload` |
| Dataset | `GET/POST/PUT/DELETE /dataset/cases` (filterable by `category`) |
| Evals | `POST /evals/run` (SSE), `GET /evals/runs[/{id}/results]`, `PATCH /evals/results/{id}` |
| Config | `GET/POST /config/hf-api-key`, `GET /config/hardware` |

## 10. Error handling

- Uniform error shape `{error: {code, message, details}}`; standard HTTP status codes.
- OOM / won't-fit local models: caught explicitly, returns a clear error naming the
  model/quant and suggesting a smaller one — never a raw traceback.
- Structured-output/tool-call retries exhausted: a distinct, explicit failure type (not
  silently treated as a normal reply), so eval assertions score it as a clean fail.
- SSE streams carry heartbeats and a terminal `error` event distinct from normal completion,
  so long local generations can be distinguished from mid-stream failures.
- Missing HF API key on a `backend: "api"` request: immediate, clear 400 rather than an
  opaque error surfaced from HF's client.

## 11. Testing strategy

- `pytest` throughout backend/tests/, mirroring the app/ package structure.
- Inference abstraction: unit tests against a fake `InferenceBackend` implementation to
  verify the tool-call loop and `PromptJsonRetrier` retry/error-feedback logic without
  needing a real model.
- Structured output: schema→GBNF grammar conversion tested against known schemas;
  `PromptJsonRetrier` tested with a scripted sequence of bad→good responses.
- Tool registry: add/reload/delete a tool file in a temp directory, verify registry state.
- Eval engine: run against an in-memory SQLite DB with a handful of fixture test cases
  covering each assertion type.
- API layer: FastAPI `TestClient` covering the full endpoint list in §9, including error
  cases from §10 (missing key, OOM simulation, retry exhaustion).
- Real local-model and real HF-API-backed tests are manual/opt-in (marked `@pytest.mark.slow`
  or similar) since they need actual downloaded weights or network+API-key access; CI runs
  the fast unit/integration suite only.

## 12. Assumptions made during design (flagged for visibility)

- **ORM**: SQLModel (typed models over SQLAlchemy) chosen for the SQLite layer — standard,
  well-documented, keeps CRUD-heavy code (dataset cases, eval results) simple without a
  bespoke query layer.
- **Docker**: deferred to Phase 2 since a meaningful `docker-compose.yml` needs both
  services; Phase 1 runs via a local Python venv (`uv` or `pip`) and `uvicorn`.
- **Tool management**: filesystem-based only, no in-app source editor, per §7.
- **HF API key storage**: persisted in `backend/.env` (loaded via `pydantic-settings`),
  never written to the SQLite DB or logged. `.env` is gitignored; `.env.example` documents
  the expected `HF_API_KEY` variable with no real value.
