# AGENTS.md — Eduvijna v1.0 Engineering Contract

This file is mandatory reading for every coding or review agent.

## Authority and execution

GitHub is the project source of truth. Work only from the active execution specification and linked architecture documents.

The development-day gate is strict:

1. Work only on the day marked ACTIVE in `.eduvijna/execution-state.yml`.
2. Do not implement future-day requirements unless they are strictly necessary to make the active day correct.
3. Never change `founder_approval` to true.
4. Never unlock the next day.
5. The next day may start only after explicit Founder approval.

## Builder and reviewer roles

- Primary implementation: Cursor Cloud Agent.
- Required Cursor implementation model: **Composer 2.5 Fast**.
- Independent engineering review: Codex.
- CI is the deterministic judge for tests, lint, type checks, builds, and migrations.

Do not run two full builders on the same task merely to duplicate work.

## Cost constraint

The complete v1.0 software-factory tooling must stay within the existing monthly subscriptions:

- ChatGPT Pro: USD 100
- Cursor Pro+: USD 60
- GitHub public repository and standard GitHub-hosted Actions

No planned usage-based overage is allowed.

Cost rules:

- Prefer Composer 2.5 Fast for Cursor implementation.
- Use deterministic tools for formatting, lint, type checking and tests.
- Keep prompts/task context scoped to the active day and relevant files.
- Avoid repeated whole-repository regeneration.
- Avoid unnecessary parallel agents.
- Do not enable paid GitHub runners or Codespaces.
- If an included quota blocks progress, stop and surface the blocker rather than enabling extra paid usage.

## Core architecture constraints

- Python 3.12 backend using FastAPI.
- React + TypeScript + Vite frontend.
- SQLAlchemy 2.x data access.
- Alembic migrations.
- SQLite for local development.
- PostgreSQL for production.
- No business logic may depend on checking `if production` to choose database behavior.
- No microservice split for v1 unless an approved architecture document explicitly requires it.
- AnythingLLM is accessed only through the Eduvijna AI/RAG adapter boundary.
- Do not scatter direct LLM-provider calls through business services.
- Agent frameworks orchestrate application services; business logic must remain testable without LangGraph.
- Public REST endpoints live under `/api/v1`.
- Tenant-aware foundations use organization, institution and actor context.
- Secrets are environment-provided and must never be committed.
- Public Git must not contain learner personal data, copyrighted bulk curriculum/coaching content, private source documents, or credentials.
- Exam and curriculum rules must carry source/version provenance.
- Generic services must not hard-code one specific examination.
- Exact requested question count is an invariant.
- Full exam replicas must obey the active versioned ExamPack blueprint.
- Diagnostic distractors must be meaningful and attributable to an error/misconception taxonomy when that subsystem is active.

## Engineering quality

Before coding:

- Read the active day spec.
- Read nearby services and tests.
- Preserve existing architecture and public contracts.
- Avoid unrelated changes.

After coding:

- run backend tests;
- run frontend typecheck/build;
- run lint;
- run migration checks;
- run the active day's acceptance suite;
- update documentation where behavior changed;
- attach concise evidence to the PR.

No failing CI may be merged.

## Pull requests

Each active day should converge on a reviewable PR that contains:

- implementation summary;
- acceptance-criteria checklist;
- tests run and results;
- migrations, if any;
- screenshots/browser evidence when UI changes;
- known limitations;
- no unrelated cleanup.

Codex review findings should be fixed on the same PR and CI rerun until all blocker/major findings are resolved.

## Founder gate

When the automated loop is green, stop implementation and mark the work ready for Founder review.

Do not start the next day.

## Cursor Cloud specific instructions

The Cloud Agent image is Ubuntu 24.04 with the Day 1 toolchain prepared on top of Cursor's default image. Active work is Day 1 in `docs/execution/D01-FOUNDATION.md`. The repository has no backend, frontend, Compose file, or dev server yet, so the environment `start` command is empty.

Toolchains:

- Python 3.12 is `/usr/bin/python3`. `python3.12-venv` and `python3-dev` are installed, so `python3 -m venv` works. SQLite is the stdlib `sqlite3` module (3.45).
- Node.js 22.22.2 is installed with nvm at `~/.nvm/versions/node/v22.22.2/bin`. Prepend that `bin` directory to `PATH` before project Node commands so `node` and `npm` come from the same install. `/exec-daemon/node` can appear earlier on `PATH` and is a different Node build.
- GNU Make and `build-essential` are already on the image.

`install` is idempotent. It checks that `python3 -m venv` works (and installs `python3.12-venv` plus `python3-dev` only when that check fails), selects the newest nvm Node, then:

- if `backend/requirements.txt` exists, creates `.venv` and runs `pip install -r backend/requirements.txt`;
- otherwise, if `backend/pyproject.toml` exists, creates `.venv` and runs `pip install -e ./backend`;
- if `frontend/package-lock.json` exists, runs `npm ci --prefix frontend`.

Docker is absent. Add it when the Day 1 Compose stack is introduced.
