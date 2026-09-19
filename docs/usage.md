# Usage

Backend-only for now (see [architecture.md](architecture.md) for the roadmap).

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in HF_API_KEY when you have one
```

## Run the API

```bash
source backend/.venv/bin/activate
uvicorn app.main:app --reload --app-dir backend
```

## Run tests

```bash
source backend/.venv/bin/activate
cd backend
pytest
```

## Run the API in Docker (alternative to the venv)

```bash
# from the repo root -- the build needs both backend/ and data/ in its context
docker build -f backend/Dockerfile -t model-workbench-backend .
docker run -p 8000:8000 model-workbench-backend
```

Note: the container's `data/` directory is ephemeral (lost when the container is removed).
Persisting it across restarts, and an `.env`/HF API key, will be addressed alongside the
docker-compose setup once the frontend exists.

## Your private test-case dataset

Real test cases go in `data/test_cases/` (gitignored, never committed). Use
`data/test_cases.template.json` as the schema reference.
