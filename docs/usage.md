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
```

## Run the API

```bash
make run   # uv run --project backend uvicorn app.main:app --reload --app-dir backend
```

## Run the frontend

Needs Node 22.22+ or 24 (CI uses Node 22).

```bash
make fe-setup   # cd frontend && npm ci
make run        # terminal 1: the API on :8000
make fe-dev     # terminal 2: Vite dev server on :5173
```

The dev server proxies `/api/*` to `http://localhost:8000` (prefix stripped), so the
frontend talks to the backend same-origin and the backend needs no CORS setup.

```bash
make fe-test    # vitest
make fe-lint    # eslint + tsc
make fe-build   # production build into frontend/dist/
```

## Run tests

```bash
make test      # application suite (what CI runs) -- skips backend/tests/ml/
make test-ml   # local-inference backend tests (torch/llama.cpp), run locally
make test-all  # everything together
make lint      # cd backend && uv run ruff check .
```

## Run the API in Docker (alternative to the venv)

```bash
make docker-build   # docker build -f backend/Dockerfile -t model-workbench-backend .
make docker-run     # docker run --rm -p 8000:8000 model-workbench-backend
```

## Before opening a PR

```bash
make ci   # backend lint+test+coverage, frontend lint/typecheck/test/build, then a Docker
          # build/boot/health check -- the same jobs GitHub Actions runs, so a pass here
          # means the PR checks will pass
```

Note: the container's `data/` directory is ephemeral (lost when the container is removed).
Persisting it across restarts, and an `.env`/HF API key, will be addressed alongside the
docker-compose setup once the frontend exists.

## Your private test-case dataset

Real test cases go in `data/test_cases/` (gitignored, never committed). Use
`data/test_cases.template.json` as the schema reference.
