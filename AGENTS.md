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

- Primary autonomous implementation: the approved zero-overage connected implementation environment.
- Cursor may be used only when it does not require usage-based/on-demand billing.
- Required model for any Cursor implementation: **Composer 2.5** (standard; not Composer 2.5 Fast).
- Dated override (2026-10-05 explicit Founder message, reconfirmed 2026-10-06): Day 5 Cursor implementation must use standard **Composer 2.5** only; do not substitute Composer 2.5 Fast.
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

- Prefer standard Composer 2.5 for Cursor implementation (not Composer 2.5 Fast unless a future explicit Founder message supersedes the 2026-10-05 override).
- Do not enable Cursor Cloud Agent on-demand billing; use the zero-overage fallback when Cloud execution is blocked.
- Use deterministic tools for formatting, lint, type checking and tests.
- Keep prompts/task context scoped to the active day and relevant files.
- Avoid repeated whole-repository regeneration.
- Avoid unnecessary parallel agents.
- Do not enable paid GitHub runners or Codespaces.
- If an included quota blocks progress, stop and surface the blocker rather than enabling extra paid usage.


## CI repair circuit breaker

Autonomous repair loops are bounded.

- A **repair iteration** is a code/document change intended to resolve the current failing CI/review set, followed by an authoritative CI run on that candidate.
- If **two consecutive repair iterations fail for the same active workstream before a green candidate is reached**, stop the autonomous repair loop. Do not launch a third full repair/CI cycle automatically.
- On stop, hand back: both candidate SHAs, CI run IDs, failing jobs/checks, whether the second failure is the same/new/flaky class, the likely root cause, and the smallest proposed next action.
- The Chief Architect/Founder must then choose one of: resume with a revised plan, narrow scope, defer an external dependency, or abandon/revert the workstream.
- Cheap targeted local/unit checks may be used between the two attempts; do not substitute repeated full CI runs for diagnosis.
- A runner outage, cancellation, rate-limit/platform incident, or other independently evidenced infrastructure failure does **not** count as a repair failure; one infrastructure retry is allowed.
- A previously approved **fail-closed external-evidence gate** (for example a formally deferred authoritative-source package) does not count as a repair failure when all engineering jobs are green and the red status is the expected recorded outcome.
- Codex findings still require closure before Founder review; the circuit breaker stops blind iteration, not review accountability.

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
