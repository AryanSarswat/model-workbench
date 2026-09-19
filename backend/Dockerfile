# Build from the repo root: docker build -f backend/Dockerfile .
# (needs both backend/ and data/ in the build context -- see the DB path note below)
FROM python:3.11-slim

WORKDIR /repo

COPY backend/ backend/
COPY data/test_cases.template.json data/test_cases.template.json

# Editable install, not a regular one: app/db.py locates data/workbench.db by climbing two
# directories up from its own __file__. A regular install copies the package into
# site-packages, which breaks that math entirely (site-packages has no relationship to this
# repo's layout). Editable install keeps __file__ pointing at /repo/backend/app/db.py, so the
# same relative-path logic that works in local dev keeps working unchanged in the container.
RUN pip install --no-cache-dir -e ./backend

WORKDIR /repo/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
