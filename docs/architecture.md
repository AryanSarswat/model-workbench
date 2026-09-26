# Architecture

## Overview

model-workbench discovers trending Hugging Face models, runs them either locally
(downloaded) or via the HF Inference API behind one common interface, and evaluates them
against a private, categorized set of test cases. Single Python backend (FastAPI), React
frontend (built after the backend is complete).

## Roadmap

- **Phase 1 (current): backend only, text-generation/chat models only.** Discovery,
  download, inference, structured output, tool calling, and evals are all implemented and
  testable via HTTP/SSE without a UI.
- **Phase 2: frontend.** Built against the Phase 1 API once the backend is solid.
- **Phase 3+: additional modalities** (vision-language, audio, image-generation,
  embeddings), each as its own `InferenceBackend` implementation plugging into the same
  registry/download/eval infrastructure — not a restructure.

## Repository layout

```
model-workbench/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, router registration
│   │   ├── config.py              # settings, hf-api-key, hardware detection
│   │   ├── models/                # SQLModel table definitions
│   │   ├── discovery/             # HF Hub trending/recent + model detail + feasibility
│   │   ├── downloads/             # download manager, job tracking, progress
│   │   ├── inference/
│   │   │   ├── base.py            # InferenceBackend protocol
│   │   │   ├── schemas.py         # ChatMessage, ChatChunk, BackendCapabilities
│   │   │   ├── registry.py        # backend name -> InferenceBackend
│   │   │   ├── hf_api_backend.py
│   │   │   ├── llama_cpp_backend.py
│   │   │   ├── transformers_backend.py
│   │   │   ├── structured_output.py  # grammar builders + PromptJsonRetrier
│   │   │   └── tool_loop.py        # tool-call orchestration
│   │   ├── tools/                  # shared tool directory, edits hot-reloadable (see below)
│   │   ├── dataset/                 # test-case CRUD, category filtering
│   │   ├── evals/                   # eval run engine, assertions, judge
│   │   └── api/                     # FastAPI routers
│   └── tests/
├── data/                            # gitignored except templates
│   └── test_cases.template.json
└── docs/
```

## Data model

**Test case** (private dataset, one file per case at `data/test_cases/<id>.json`, gitignored):

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

`category` is a free-form string, not a fixed enum — the template suggests `coding`,
`general`, `world_understanding`, `personalization`, but new categories need no code
change. Every field except `id`, `category`, and `messages` is optional.

**SQLite** (`data/workbench.db`, gitignored, local only — no multi-device sync):
`chat_sessions`, `chat_messages`, `downloaded_models`, `eval_runs`, `eval_results`,
`response_metrics` (recorded per chat turn, not just evals — tokens/sec, TTFT, latency,
cost, RAM/VRAM). SQLite over Postgres because this is single-user/single-machine and needs
no server; SQLite over plain JSON (unlike the test-case dataset) because eval reporting
needs real aggregation (`GROUP BY model, backend, category`).

## Inference engine

**Common interface**, so callers depend on the shape, not a specific backend:

```python
class InferenceBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...
    async def stream_chat(self, model_id: str, messages: list[ChatMessage], tools: list[ToolSpec] | None = None, output_schema: dict | None = None) -> AsyncIterator[ChatChunk]: ...
    async def aclose(self) -> None: ...
```

`stream_chat(..., output_schema=...)` carries a raw JSON-Schema dict
(`ChatRequest.output_schema`); invalid schemas are a 400 `invalid_output_schema`
pre-stream, never mid-stream. `get_backend(name, ...)` in
`app/inference/registry.py` resolves a request's `backend` field to a concrete
implementation; `POST /chat/stream` calls that instead of importing a specific backend
class, so it's the one thing that has to change when a new backend is added, not every
caller.

Three implementations: `HFInferenceAPIBackend` (remote, via
`huggingface_hub.AsyncInferenceClient` — genuinely async, so a slow provider response
doesn't block the event loop; which `model_id`s actually work depends on HF routing to an
enabled provider, surfaced as a normal 4xx rather than a crash). `LlamaCppBackend` (GGUF via
llama-cpp-python, runs on any hardware) resolves its file from the downloaded-models table
in the registry (`repo_id`, or `repo_id:filename` when several quants are on disk) and
keeps the loaded model in a process-wide cache — no eviction, a deliberate single-user
simplicity trade-off. `TransformersBackend` (fallback for models
without a GGUF build; MPS/CUDA/CPU auto-detected) resolves its snapshot dir from the
downloaded-models table by plain `repo_id` and keeps the loaded model in a process-wide
cache like the llama.cpp backend. Unconstrained generation streams via
`TextIteratorStreamer` and runs to EOS with no token cap; schema-guided/tool
turns are non-streamed (one delta + done, 512-token cap on transformers
guided turns).

Chat sessions are a persistence record, not context management: `POST /chat/sessions`
creates a session, `POST /chat/stream` takes an optional `session_id` and files the new
user turn plus the completed assistant reply (nothing on error/disconnect), and
`GET/DELETE /chat/sessions[/{id}]` list, show (with ordered messages), and delete.
Inference stays stateless — the caller still resends full history every request.

**Structured output** (`POST /chat/stream` `output_schema`, raw JSON-Schema dict):

| Backend | Mechanism | Guarantee |
|---|---|---|
| llama.cpp | `LlamaGrammar.from_json_schema` GBNF grammar | Guaranteed valid |
| transformers | `outlines` `get_json_schema_logits_processor` LogitsProcessor (local extra) | Guaranteed valid |
| HF Inference API | `PromptJsonRetrier` schema loop (prompt + parse + retry, ≤5 turns) | Best-effort |

Constrained turns never stream (final JSON as one delta + done); transformers
guided turns cap at `max_new_tokens=512`, unconstrained chat still streams to EOS
uncapped. `tools` + `output_schema` runs the tool loop first, then constrains the
final reply (loop turns stay unconstrained). Invalid schemas are a 400
`invalid_output_schema` pre-stream.

`capabilities()` reports which mode is active, so a response can be labeled
"grammar-enforced" vs "best-effort" — this feeds eval assertions too.

**Tool calling:** tools live in `backend/app/tools/` (below). llama.cpp uses native
`tools=[...]` (`tool_choice="auto"`); the other backends run the shared `run_tool_loop`
over `PromptJsonRetrier`'s `{"tool": ..., "arguments": {...}} | {"reply": ...}` schema —
the same retry/error-feedback loop as the structured-output fallback, not a separate
code path. On a tool call, we execute the function, append the result, and continue, up
to `max_iterations` (default 5) model turns. Fallback-loop traffic rides as user-role
messages so `ChatMessage` stays `system|user|assistant` (only llama.cpp's native loop
uses `tool`-role dicts, internally). Tool-calling turns are non-streamed; the final
reply yields as one delta + done. `tool_calling_mode` recording is deferred to the eval
engine, which is where the signal gets consumed.

## Shared tools directory

`backend/app/tools/` is the single source of truth for available tools — no database to
keep in sync:

```python
TOOL_SPEC = ToolSpec(name="calculator", description="...", parameters={...})
async def run(args: dict) -> str: ...
```

Modify = edit + `POST /tools/reload`. Add = new file + one line in `_TOOL_MODULE_NAMES`
+ restart. Delete = remove the file and its `_TOOL_MODULE_NAMES` line + restart (reload
only re-imports modules already listed, so it can't add or drop one). A chat request filters to a subset via `tools: [...]`
(tool names), so a new tool can be tested against one model without exposing it
everywhere else. Filesystem-based management only — no in-app source editor
(deliberate simplicity choice).

## Eval engine

```
POST /evals/run { model_id, backend, category?, judge_model_id? }
```

Every matching test case runs through the same chat path used for regular chat — no
eval-specific inference logic. Automatically recorded per case: response, structured
output/tool-calling modes and retry counts, and performance metrics. Assertions run
automatically; if a case has `judge.criteria`, a second call to `judge_model_id` scores it.
Every result also carries `manual_verdict`/`manual_notes` for hand review regardless of
automated results. The backend is resolved once before the stream starts, so misconfiguration
(missing key, undownloaded model) is a normal 4xx. A per-case failure (backend error,
invalid case schema) is recorded on that result's `error` and the run continues; a run
always ends `completed` or `failed` with a final `done` event. Aggregating `eval_results` by `(model_id, backend, category)` produces
the model-comparison report: pass rate, avg tokens/sec, avg cost, tool-calling reliability
%, structured-output reliability %.

## Discovery, downloads, and feasibility

- `GET /models/discover?sort=trending|recent` — `recent` sorts by `createdAt` so new
  releases surface before they've accumulated likes/downloads.
- `GET /models/{id}/feasibility?quant=...` — estimates memory requirement (GGUF: file size
  + ~20% overhead; transformers: param count × bytes-per-dtype) against detected
  RAM/VRAM/GPU (`GET /config/hardware`), returns `comfortable | tight | wont_fit` +
  reasoning. Advisory, not a hard block.
- `POST /models/{id}/download` — either one GGUF file (`filename` from `gguf_files`)
  or a whole transformers snapshot (`snapshot: true` -- every non-GGUF file in the repo,
  into `models/<repo>/snapshot/`). Both stream directly (not via `hf_hub_download`,
  which has no progress-callback hook) so `GET /models/downloads/{job_id}` can be
  polled for real byte-level `{status, percent, detail}` -- snapshot percent is
  aggregate bytes over the summed Hub-reported sizes. Runs as a FastAPI background
  task, not SSE (unlike eval runs, which stream `{completed, total, current_case}`);
  downloads may move to SSE too once there's a frontend to stream it to.

## API surface

| Area | Endpoints |
|---|---|
| Discovery/downloads | `GET /models/discover`, `GET /models/{id}`, `GET /models/{id}/feasibility`, `POST /models/{id}/download`, `GET /models/downloads`, `GET /models/downloads/{job_id}`, `GET /models/downloaded`, `DELETE /models/downloaded/{id}` |
| Chat | `POST /chat/stream` (SSE), `GET/DELETE /chat/sessions[/{id}]` |
| Tools | `GET /tools`, `POST /tools/reload` |
| Dataset | `GET/POST/PUT/DELETE /dataset/cases` (filterable by `category`) |
| Evals | `POST /evals/run` (SSE), `GET /evals/runs[/{id}/results]`, `PATCH /evals/results/{id}` |
| Config | `GET/POST /config/hf-api-key`, `GET /config/hardware` |

## Error handling

- Uniform error shape `{error: {code, message, details}}`; standard HTTP status codes.
- OOM/won't-fit local models: caught explicitly, names the model/quant, suggests a smaller
  one — never a raw traceback.
- Structured-output/tool-call retries exhausted: a distinct failure type, scored as a clean
  fail by eval assertions rather than crashing or silently passing.
- SSE streams carry heartbeats and a terminal `error` event distinct from normal completion.
- Missing HF API key on a `backend: "api"` request: immediate 400, not an opaque HF error.

## Notable decisions

- **ORM**: SQLModel over raw SQL — typed models, standard, keeps CRUD-heavy code simple.
- **Docker**: `backend/Dockerfile` builds and runs the backend standalone (build from the
  repo root: `docker build -f backend/Dockerfile .`, since it needs both `backend/` and
  `data/` in the build context). A root `docker-compose.yml` chaining backend + frontend is
  still deferred until the frontend exists — one service alone doesn't need compose. Local
  dev still defaults to a Python venv + uvicorn; the image is for anyone who'd rather not
  set up Python locally, and lays groundwork for the eventual compose file.
- **HF API key**: `backend/.env` via `pydantic-settings`, never in the DB or logs.
