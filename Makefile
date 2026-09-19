.PHONY: setup run test lint lock docker-build docker-run

setup:
	cd backend && uv sync --extra dev

run:
	uv run --project backend uvicorn app.main:app --reload --app-dir backend

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .

lock:
	cd backend && uv lock

docker-build:
	docker build -f backend/Dockerfile -t model-workbench-backend .

docker-run:
	docker run --rm -p 8000:8000 model-workbench-backend
