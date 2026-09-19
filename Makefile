.PHONY: setup run test lint ci lock docker-build docker-run docker-ci

setup:
	cd backend && uv sync --extra dev

run:
	uv run --project backend uvicorn app.main:app --reload --app-dir backend

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .

# Mirrors both GitHub Actions jobs (`backend` + `docker`) so a pass here is a real signal
# the PR checks will pass -- catching a Docker-only failure locally is a lot cheaper than
# a push-wait-fail-fix round trip.
ci:
	cd backend && uv sync --locked --extra dev
	cd backend && uv run ruff check .
	cd backend && uv run pytest --cov --cov-report=term-missing
	$(MAKE) docker-ci

lock:
	cd backend && uv lock

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
