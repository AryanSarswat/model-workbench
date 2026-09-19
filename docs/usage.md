# Usage

Backend-only for now (see [architecture.md](architecture.md) for the roadmap).

Dependencies are managed with [uv](https://docs.astral.sh/uv/); `backend/uv.lock` pins
exact versions so local dev, CI, and Docker all install the same thing. A root `Makefile`
wraps the common commands below — prefer `make <target>` day to day.

## Setup

```bash
make setup   # cd backend && uv sync --extra dev
cd backend && cp .env.example .env   # fill in HF_API_KEY when you have one
```

## Run the API

```bash
make run   # uv run --project backend uvicorn app.main:app --reload --app-dir backend
```

## Run tests

```bash
make test   # cd backend && uv run pytest
make lint   # cd backend && uv run ruff check .
```

## Run the API in Docker (alternative to the venv)

```bash
make docker-build   # docker build -f backend/Dockerfile -t model-workbench-backend .
make docker-run     # docker run --rm -p 8000:8000 model-workbench-backend
```

Note: the container's `data/` directory is ephemeral (lost when the container is removed).
Persisting it across restarts, and an `.env`/HF API key, will be addressed alongside the
docker-compose setup once the frontend exists.

## Your private test-case dataset

Real test cases go in `data/test_cases/` (gitignored, never committed). Use
`data/test_cases.template.json` as the schema reference.
