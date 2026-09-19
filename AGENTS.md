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
- **CI must stay green.** Every push runs lint (`ruff check`) and `pytest --cov` via GitHub
  Actions (`.github/workflows/ci.yml`). The `backend` check is a required status check on
  `main` — a PR literally cannot merge until it passes.
- **Private dataset never gets committed.** `data/test_cases/` and `data/*.db` are
  gitignored. Only `data/test_cases.template.json` is tracked.
- **Structured output & tool calling share one fallback mechanism** (`PromptJsonRetrier`) —
  don't build a second one-off JSON-extraction path for a new feature; extend the shared one.

## Contributing (PRs only)

`main` is protected — every change lands via a pull request the user reviews and merges
themselves; there is no direct push. For any agent working in this repo:

- **One focused change per PR.** No big-bang PRs that bundle unrelated work. If a task
  naturally splits into independent pieces (e.g. "add CI coverage" and "implement a
  feature"), open separate PRs for each rather than one large one.
- **Title states the change, not the ticket.** e.g. `feat: implement GPU detection for
  hardware feasibility check`, not `Updates` or `Changes per request`.
- **Description stays focused**: what changed and why, using the PR template
  (`.github/pull_request_template.md`) — summary, scope (what's deliberately excluded),
  and how it was tested. Not a changelog of every file touched.
- **No AI slop.** No filler sentences, no restating the diff in prose, no padding a
  description to look thorough. If there's nothing more to say than the summary, stop there.
- **Small, incremental commits within the PR** — each commit should be a coherent step, not
  a single "implement everything" commit for a multi-part change.
- **Every PR must be reviewable**: keep the diff small enough that a human can actually read
  it in one sitting. If a change is growing beyond that, stop and split it.

## Commands

```bash
cd backend
source .venv/bin/activate     # create with: python3 -m venv .venv
pip install -e ".[dev]"
pytest                         # run tests
ruff check .                   # lint
uvicorn app.main:app --reload --app-dir backend   # run the API (from repo root)
```
