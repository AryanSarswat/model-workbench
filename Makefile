.PHONY: setup run test test-ml test-all lint ci lock docker-build docker-run docker-ci \
	fe-setup fe-dev fe-test fe-lint fe-build fe-ci

# Local dev gets everything, including the heavy `local` extra (torch/llama.cpp)
# that CI deliberately skips -- without it tests/ml/ can't even be collected.
setup:
	cd backend && uv sync --extra dev --extra local

run:
	uv run --project backend uvicorn app.main:app --reload --app-dir backend

# `test` is the application suite (what CI runs). ML backend tests live in
# backend/tests/ml/ and run locally via `test-ml` or together with everything via
# `test-all`. Splitting by directory with --ignore (not -m 'not ml') so CI skips ML
# collection entirely. NOTE: app modules still import torch/transformers/llama.cpp at
# top level via the registry -- dropping the heavy install from CI needs lazy imports
# (a separate change, deliberately not done here).
test:
	cd backend && uv run pytest tests --ignore=tests/ml

test-ml:
	cd backend && uv run pytest tests/ml

test-all:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .

# Local pre-PR gate: everything the GitHub Actions jobs run (`backend`, `frontend`,
# `docker`), PLUS the ML suite CI skips -- so a pass here means the PR checks will pass
# AND the locally-run ML tests are green. Catching either failure locally is a lot
# cheaper than a push-wait-fail-fix round trip.
ci:
	cd backend && uv sync --locked --extra dev --extra local
	cd backend && uv run ruff check .
	cd backend && uv run pytest --cov --cov-report=term-missing
	$(MAKE) fe-ci
	$(MAKE) docker-ci

lock:
	cd backend && uv lock

# Frontend (frontend/, Vite + React). `fe-dev` proxies /api to `make run` on :8000,
# so run both side by side.
fe-setup:
	cd frontend && npm ci

fe-dev:
	cd frontend && npm run dev

fe-test:
	cd frontend && npm test

fe-lint:
	cd frontend && npm run lint
	cd frontend && npm run typecheck

fe-build:
	cd frontend && npm run build

# Same sequence as the `frontend` CI job.
fe-ci:
	cd frontend && npm ci
	$(MAKE) fe-lint
	$(MAKE) fe-test
	$(MAKE) fe-build

docker-build:
	docker build -f backend/Dockerfile -t model-workbench-backend .

docker-run:
	docker run --rm -p 8000:8000 model-workbench-backend

# Same build-boot-health sequence as the `docker` CI job, self-contained so it can run
# standalone or as part of `make ci`. Always tears the container down, pass or fail.
docker-ci:
	docker build -f backend/Dockerfile -t model-workbench-backend:ci .
	docker rm -f backend-ci >/dev/null 2>&1 || true
	docker run -d --name backend-ci -p 8000:8000 model-workbench-backend:ci >/dev/null
	@for i in $$(seq 1 30); do \
		if curl -sf http://localhost:8000/health >/dev/null; then \
			echo "container healthy"; \
			docker rm -f backend-ci >/dev/null; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Container did not become healthy within 30s"; \
	docker logs backend-ci; \
	docker rm -f backend-ci >/dev/null; \
	exit 1
