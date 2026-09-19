.PHONY: setup run test lint ci lock docker-build docker-run

setup:
	cd backend && uv sync --extra dev

run:
	uv run --project backend uvicorn app.main:app --reload --app-dir backend

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .

# Mirrors the `backend` CI job exactly (install from the lockfile, lint, test with
# coverage) so a failure here means the PR check will fail too. Doesn't include the
# `docker` job -- that's a much slower image build/boot check; run it separately with
# `make docker-build docker-run` when Dockerfile or dependency changes warrant it.
ci:
	cd backend && uv sync --locked --extra dev
	cd backend && uv run ruff check .
	cd backend && uv run pytest --cov --cov-report=term-missing

lock:
	cd backend && uv lock

docker-build:
	docker build -f backend/Dockerfile -t model-workbench-backend .

docker-run:
	docker run --rm -p 8000:8000 model-workbench-backend
