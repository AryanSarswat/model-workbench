# Build from the repo root: docker build -f backend/Dockerfile .
# (needs both backend/ and data/ in the build context -- see the DB path note below)
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv

WORKDIR /repo

COPY backend/ backend/
COPY data/test_cases.template.json data/test_cases.template.json

WORKDIR /repo/backend

# uv sync installs the project itself in editable mode (same as `pip install -e .`), so
# app/db.py's __file__-based DB path resolution keeps working unchanged inside the
# container. --locked fails the build instead of silently re-resolving if uv.lock is out
# of sync with pyproject.toml. No --extra dev: the runtime image only needs the app's own
# dependencies, not pytest/ruff.
RUN uv sync --locked

ENV PATH="/repo/backend/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
