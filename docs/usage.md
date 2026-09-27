# Usage

Backend (FastAPI, `backend/`) and frontend (Vite + React, `frontend/`); see
[architecture.md](architecture.md) for the design and roadmap.

Dependencies are managed with [uv](https://docs.astral.sh/uv/); `backend/uv.lock` pins
exact versions so local dev, CI, and Docker all install the same thing. A root `Makefile`
wraps the common commands below — prefer `make <target>` day to day.

## Setup

```bash
make setup   # cd backend && uv sync --extra dev --extra local
cd backend && cp .env.example .env   # fill in HF_API_KEY when you have one
```

The `local` extra (torch, transformers, llama-cpp-python) powers the `gguf` /
`transformers` backends and is installed for local dev and Docker, but not in CI --
CI runs the application suite only (see `make test` below), which must pass without it.
A local request for a backend whose extra is missing fails as a 400
(`backend_not_available`) naming the missing packages, not an import traceback.

## Run the API

```bash
make run   # uv run --project backend uvicorn app.main:app --reload --app-dir backend
```

## Run the frontend

Needs Node 22.22+ or 24 (CI uses Node 22).

```bash
make fe-setup   # cd frontend && npm ci
make dev        # both at once, in one terminal (Ctrl+C stops both)
# or separately:
make run        # terminal 1: the API on :8000
make fe-dev     # terminal 2: Vite dev server on :5173
```

The dev server proxies `/api/*` to `http://localhost:8000` (prefix stripped), so the
frontend talks to the backend same-origin and the backend needs no CORS setup.

```bash
make fe-test    # vitest
make fe-lint    # eslint + tsc
make fe-build   # production build into frontend/dist/
make fe-types   # regenerate the frontend's API types from the backend's OpenAPI schema
```

The frontend's API types are generated, not hand-written: after changing a backend
request/response model, run `make fe-types` and commit the two files it rewrites
(`frontend/openapi.json`, `frontend/src/api/schema.gen.ts`). CI fails when either is stale.

## Run tests

```bash
make test      # application suite (what CI runs) -- skips backend/tests/ml/
make test-ml   # local-inference backend tests (torch/llama.cpp), run locally
make test-all  # everything together
make lint      # cd backend && uv run ruff check . && uv run ruff format --check .
make format    # cd backend && uv run ruff format .
```

## Run the API in Docker (alternative to the venv)

```bash
make docker-build   # docker build -f backend/Dockerfile -t model-workbench-backend .
make docker-run     # docker run --rm -p 8000:8000 model-workbench-backend
```

## Before opening a PR

```bash
make ci   # backend lint+test+coverage, generated-API-types check, frontend
          # lint/typecheck/test/build, then a Docker build/boot/health check -- the same
          # jobs GitHub Actions runs, so a pass here means the PR checks will pass
```

Note: the container's `data/` directory is ephemeral (lost when the container is removed).
Persisting it across restarts, and passing an `.env`/HF API key into the container, are
not set up yet.

## Your private test-case dataset

Real test cases go in `data/test_cases/` (gitignored, never committed). Use
`data/test_cases.template.json` as the schema reference.
