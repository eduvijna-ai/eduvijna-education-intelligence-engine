# Day 9 — D9-36 final acceptance evidence

## D9-36 gate summary (honest state)

| Gate | Status |
|------|--------|
| `CODE_REVIEW_CLEAN` | **YES** — SHA `eede5d67048502211d867ba45390b43c4f820f1d` |
| `TARGETED_CI_EXACT_HEAD_GREEN` | **YES** — last verified: PR CI **#68** / `39096557003` on `13fbd6426130e3ee46e8f056d75c339b7a685482` (see PR for newer HEAD) |
| `FULL_PYTEST_CURSOR_REPORTED_GREEN` | **YES** (exit 0, 1784 collected, 0 failed observed) — **passed/skipped/xfail counts UNVERIFIED** (see `D09-D36-FULL-PYTEST-EVIDENCE.md`) |
| `COMPOSE_SMOKE` | **BLOCKED** — `BLOCKED_DOCKER_UNAVAILABLE` on Cursor VM; see `D09-D36-FOUNDER-COMPOSE-SMOKE.md` |
| `D9_36_FINAL_ACCEPTANCE` | **BLOCKED** — pending Compose evidence or Founder documented exception |
| `DAY_10` / merge | **LOCKED** — PR #27 Draft, unmerged; `founder_approval: false` |

Manual **code** review remains clean. Final engineering acceptance is **blocked on evidence**, not failed code.

| Field | Value |
|-------|--------|
| Manual code review CLEAN SHA (application code) | `eede5d67048502211d867ba45390b43c4f820f1d` |
| Frozen code acceptance candidate | `eede5d67048502211d867ba45390b43c4f820f1d` |
| PR branch | #27 `feature/day9-diagnostic-distractor-intelligence` → `develop` (Draft, unmerged) |
| Last independently verified docs HEAD | `13fbd6426130e3ee46e8f056d75c339b7a685482` — targeted CI **#68** / `39096557003` SUCCESS (2026-10-18) |
| Current PR HEAD | **See GitHub PR #27** (docs-only commits may advance HEAD without re-stating here) |

## D9-36 checklist

| Step | Result | Notes |
|------|--------|-------|
| Evidence map updated | `D09-SCOPE-MAP.md` | D9-36 pending Founder |
| `EDUVIJNA_CANDIDATE_SHA` | `eede5d6…` | Verifiers on frozen code SHA |
| Full `pytest tests/` | See `D09-D36-FULL-PYTEST-EVIDENCE.md` | One-time run; no default re-run |
| `python -m app.day8_verify` | PASS | Targeted CI + local |
| `python -m app.day9_verify --json` | `ok: true` | Targeted CI + local |
| Compose smoke | **BLOCKED** | Founder checklist in `D09-D36-FOUNDER-COMPOSE-SMOKE.md` |
| Migrations / Postgres | Green (reported) | No Day-9 DDL; Alembic check + `test_postgres_compile.py` |

## Full historical regression

Documented in **`docs/execution/D09-D36-FULL-PYTEST-EVIDENCE.md`** (metadata, limitations, sanitized excerpt).

## Founder verifiers (JSON) — host / CI only

Exact-SHA checks require a Git checkout on the **host** (or CI runner), not the backend container image. Targeted PR CI runs these at the verified commit.

```bash
export EDUVIJNA_CANDIDATE_SHA="$(git rev-parse HEAD)"   # or frozen code SHA when auditing that revision
cd backend && python -m app.day8_verify && python -m app.day9_verify --json
```

Compose container smoke: **`D09-D36-FOUNDER-COMPOSE-SMOKE.md`** (section B — no in-container `day8_verify` / `day9_verify`).

## D9-29…D9-35 demonstration trace

Unchanged — see prior sections in git history; scope map links tests and `day9_verify` checks.

## Persistence / compatibility (D9-33)

- No new Day-9 tables; taxonomy JSON + `OrchestrationAuditEvent` / Day-8 checkpoint tables.
- SQLite: `alembic upgrade head` + `alembic check` (head `20261015_0014`).
- PostgreSQL: static DDL compile test only unless live instance run separately.

## Governance

- PR #27 **Draft**; **not merged**.
- Day 10 **LOCKED**; D5-DS01 / issue #16 unchanged.
- No Codex.

## Founder acceptance

**Not complete.** Do not seek Founder signoff for full D9-36 until Compose smoke is executed (or Founder explicitly accepts documented Compose risk) and regression footer counts are accepted or re-verified.
