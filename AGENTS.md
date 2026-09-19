# Agent notes

Context for any coding agent (or human) working in this repo.

## What this is

A backend-first project. See [docs/architecture.md](docs/architecture.md) for the full
design and [docs/usage.md](docs/usage.md) for setup/run/test commands. Do not build
frontend code yet — the backend is being completed first, end-to-end, before Phase 2
(frontend) starts.

## Working conventions

- **Tests: real functionality only.** Cover the actual behavior a module exists for. Do not
  add exhaustive edge-case/parametrized test matrices — that bloats the repo without adding
  much confidence for a project this size. A module needs a handful of focused tests, not
  dozens.
- **Repo contains code and docs only.** No dated spec documents, no implementation plan
  files — those are working documents for getting from idea to code, not repo artifacts.
  Living reference docs belong in `docs/*.md` and should be kept up to date as the
  architecture evolves; specs/plans (if produced during a work session) are gitignored
  under `docs/superpowers/`.
- **CI must stay green.** Every push runs lint (`ruff check`) and `pytest` via GitHub
  Actions (`.github/workflows/ci.yml`). Don't merge/push code that breaks either.
- **Private dataset never gets committed.** `data/test_cases/` and `data/*.db` are
  gitignored. Only `data/test_cases.template.json` is tracked.
- **Structured output & tool calling share one fallback mechanism** (`PromptJsonRetrier`) —
  don't build a second one-off JSON-extraction path for a new feature; extend the shared one.

## Commands

```bash
cd backend
source .venv/bin/activate     # create with: python3 -m venv .venv
pip install -e ".[dev]"
pytest                         # run tests
ruff check .                   # lint
uvicorn app.main:app --reload --app-dir backend   # run the API (from repo root)
```
