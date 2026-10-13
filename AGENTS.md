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


## Bounded implementation / review loop

Every implementation task follows one bounded autonomous loop:

1. ChatGPT / Chief Architect posts the authoritative handoff to Cursor.
2. Cursor implements the task using standard Composer 2.5 and runs only impacted tests during iteration work.
3. Cursor pushes one exact candidate SHA and posts `EDUVIJNA_CURSOR_COMPLETE <40-char-head-sha>` with test evidence.
4. Repository automation marks the PR ready if needed and requests Codex review on that exact SHA.
5. If Codex has unresolved findings, repository automation assigns those findings back to Cursor on the same PR as the next iteration.
6. Cursor repairs only those findings, posts a new exact completion marker, and Codex re-reviews.
7. If Codex has no unresolved findings, automated implementation stops and the task moves to the Chief Architect / Founder gate.

Iteration rules:

- Cursor must keep `.eduvijna/pytest-targets.txt` scoped to the currently implemented/repaired task before posting its completion marker.
- PR CI and Compose backend pytest consume that same target file; they must not run unrelated historical pytest modules during implementation/review iterations.
- One **task iteration** = one Cursor implementation/repair candidate followed by one Codex review of that exact candidate.
- Maximum = **3 total iterations for the same task**, including the initial implementation.
- If Codex still reports unresolved findings after iteration 3, immediately **STOP_AND_ESCALATE**. Never start iteration 4 automatically.
- Infrastructure outage/cancellation/rate-limit events do not consume an iteration when independently evidenced.
- Do not change task scope between iterations. New scope is a new Founder/Chief Architect decision.
- No automatic merge and no automatic next-day unlock.

## CI repair circuit breaker

CI repair follows the same bounded philosophy.

- A **repair iteration** is a code/document change intended to resolve the current failing CI/review set, followed by the smallest authoritative test set needed for that change.
- Maximum autonomous repair iterations for the same active workstream: **3**.
- After the third failed iteration, immediately `STOP_AND_ESCALATE`.
- On stop, hand back candidate SHAs, CI/check IDs, failing checks, failure classification, likely root cause, and the smallest proposed next action.
- Use targeted unit/integration checks during repair. Do not repeat the full historical regression unless shared infrastructure/migrations changed or the task has reached its final acceptance checkpoint.
- A runner outage, cancellation, rate-limit/platform incident, or other independently evidenced infrastructure failure does **not** count as a repair failure.
- A previously approved fail-closed external-evidence gate does not count as a repair failure when engineering checks are green and the red outcome is the expected recorded gate.
- Codex findings require closure before Founder review unless the Founder explicitly authorizes a documented exception.

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
