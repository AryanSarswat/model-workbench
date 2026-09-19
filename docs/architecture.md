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
│   │   │   ├── base.py            # InferenceBackend protocol, BackendCapabilities
│   │   │   ├── llama_cpp_backend.py
│   │   │   ├── transformers_backend.py
│   │   │   ├── hf_api_backend.py
│   │   │   ├── structured_output.py  # grammar builders + PromptJsonRetrier
│   │   │   └── tool_loop.py        # tool-call orchestration
│   │   ├── tools/                  # shared, hot-reloadable tool directory (see below)
│   │   ├── dataset/                 # test-case CRUD, category filtering
│   │   ├── evals/                   # eval run engine, assertions, judge
│   │   └── api/                     # FastAPI routers
│   └── tests/
├── data/                            # gitignored except templates
│   └── test_cases.template.json
└── docs/
```

## Data model

**Test case** (private dataset, `data/test_cases/*.json`, gitignored):

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

**Common interface**, so the frontend never touches a specific backend:

```python
class InferenceBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...
    async def stream_chat(self, messages, tools=None, output_schema=None) -> AsyncIterator[ChatChunk]: ...
```

Three implementations: `LlamaCppBackend` (GGUF via llama-cpp-python, runs on any hardware),
`TransformersBackend` (fallback for models without a GGUF build; MPS/CUDA/CPU
auto-detected), `HFInferenceAPIBackend` (remote, via `huggingface_hub.InferenceClient`).

**Structured output:**

| Backend | Mechanism | Guarantee |
|---|---|---|
| llama.cpp | JSON Schema → GBNF grammar | Guaranteed valid |
| transformers | `outlines` guided generation | Guaranteed valid |
| HF Inference API | Prompt + parse + retry (`PromptJsonRetrier`) | Best-effort |

`capabilities()` reports which mode is active, so a response can be labeled
"grammar-enforced" vs "best-effort" — this feeds eval assertions too.

**Tool calling:** tools live in `backend/app/tools/` (below). If the model's chat template
natively supports `tools=[...]`, we use it; otherwise `PromptJsonRetrier` handles a
`{tool_call: {...}} | {reply: string}` schema — the same retry/error-feedback loop used for
structured-output fallback, not a separate code path. On a tool call, we execute the
function, append the result as a `tool`-role message, and continue, up to
`max_tool_iterations` (default 5). Every response records `tool_calling_mode`
(`native`/`fallback`/`failed`) and `structured_output_mode`, plus retry counts — these
double as eval signals for free.

## Shared tools directory

`backend/app/tools/` is the single source of truth for available tools — no database to
keep in sync:

```python
TOOL_SPEC = ToolSpec(name="calculator", description="...", args_schema={...})
async def run(args: dict) -> Any: ...
```

Add = new file. Modify = edit + `POST /tools/reload`. Delete = remove file + reload. A chat
or eval request can filter to a subset via `tool_names: [...]`, so a new tool can be tested
against one model without exposing it everywhere else. Filesystem-based management only —
no in-app source editor (deliberate simplicity choice).

## Eval engine

```
POST /evals/run { model_id, backend, category?, judge_model_id? }
```

Every matching test case runs through the same chat path used for regular chat — no
eval-specific inference logic. Automatically recorded per case: response, structured
output/tool-calling modes and retry counts, and performance metrics. Assertions run
automatically; if a case has `judge.criteria`, a second call to `judge_model_id` scores it.
Every result also carries `manual_verdict`/`manual_notes` for hand review regardless of
automated results. Aggregating `eval_results` by `(model_id, backend, category)` produces
the model-comparison report: pass rate, avg tokens/sec, avg cost, tool-calling reliability
%, structured-output reliability %.

## Discovery, downloads, and feasibility

- `GET /models/discover?sort=trending|recent` — `recent` sorts by `createdAt` so new
  releases surface before they've accumulated likes/downloads.
- `GET /models/{id}/feasibility?quant=...` — estimates memory requirement (GGUF: file size
  + ~20% overhead; transformers: param count × bytes-per-dtype) against detected
  RAM/VRAM/GPU (`GET /config/hardware`), returns `comfortable | tight | wont_fit` +
  reasoning. Advisory, not a hard block.
- Downloads and eval runs report structured progress (`{step, percent, detail}` /
  `{completed, total, current_case}`) over SSE, backed by `tqdm` server-side for terminal
  visibility when running natively.

## API surface

| Area | Endpoints |
|---|---|
| Discovery/downloads | `GET /models/discover`, `GET /models/{id}`, `GET /models/{id}/feasibility`, `POST /models/{id}/download`, `GET /models/downloads/{job_id}`, `GET /models/downloaded`, `DELETE /models/downloaded/{id}` |
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
