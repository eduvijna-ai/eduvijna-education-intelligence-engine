# Day 9 — D9-36 final acceptance evidence

Last independently verified as of **2026-10-19** (Chief Architect spec-closure CLEAN at code SHA below).

## D9-36 gate summary (honest state)

| Gate | Status |
|------|--------|
| `CODE_REVIEW_CLEAN` | **YES** — `e1608dd60eb0604b2d68d307e2a7e90db4afbbec` (SC-R6 round-6 repair review CLEAN) |
| `TARGETED_CI_EXACT_CODE_SHA_GREEN` | **YES** — PR CI **#76** / run `39248106313` on `e1608dd…` (197 targeted tests reported) |
| `FULL_PYTEST_NEW_FROZEN_SHA` | **PASS** — `1839 passed`, 0 failed, exit 0 (~35.2 min); see `D09-D36-FULL-PYTEST-EVIDENCE.md` |
| `COMPOSE_SMOKE` | **BLOCKED** — `BLOCKED_DOCKER_UNAVAILABLE` on Cursor VM; Founder steps in `D09-D36-FOUNDER-COMPOSE-SMOKE.md` |
| `D9_36_FINAL_ACCEPTANCE` | **BLOCKED** — full regression green on frozen SHA; pending Compose evidence or Founder documented Compose-risk exception |
| `DAY_10` / merge | **LOCKED** — PR #27 Draft, unmerged; `founder_approval: false` |

| Field | Value |
|-------|--------|
| Frozen code acceptance candidate | `e1608dd60eb0604b2d68d307e2a7e90db4afbbec` |
| PR branch | #27 `feature/day9-diagnostic-distractor-intelligence` → `develop` (Draft, unmerged) |
| Current PR HEAD (code + docs) | Same as frozen candidate unless docs-only commits follow (see GitHub PR #27) |

## D9-36 checklist

| Step | Result | Notes |
|------|--------|-------|
| Evidence map updated | `D09-SCOPE-MAP.md` | D9-36 row updated for `e1608dd…` |
| `EDUVIJNA_CANDIDATE_SHA` | `e1608dd…` | Matches checkout HEAD |
| Full `pytest tests/` | **PASS** | `pytest tests --tb=short -ra`; 1839 passed; log artifact `d9-36-full-pytest-e1608dd.log` |
| `python -m app.day8_verify` | **PASS** | Host run; artifact `d9-36-day8-verify-e1608dd.txt` |
| `python -m app.day9_verify --json` | **`ok: true`** | 52 checks; artifact `d9-36-day9-verify-e1608dd.json` |
| Compose smoke | **BLOCKED** | No Docker on Cursor VM |
| Migrations / Postgres | **PASS (SQLite)** / static PG | No Day-9 DDL; `alembic upgrade head` + `check` on `migration-d936-e1608dd.db`; `test_postgres_compile.py` pass (no live Postgres) |

## Founder verifiers (host / CI)

Exact-SHA checks require a Git checkout on the **host** (or CI runner), not the backend container image.

```bash
export EDUVIJNA_CANDIDATE_SHA="$(git rev-parse HEAD)"
cd backend && python -m app.day8_verify && python -m app.day9_verify --json
```

Targeted PR CI #76 runs the same verifiers at `e1608dd…`.

## Spec-closure highlights (SC-R1…R6)

| Area | Evidence |
|------|----------|
| Citation label + visible snippet binding | `validators/evidence_ref.py`, `grounding.py`; `test_day9_sc_r6_acceptance.py`; `orphan_trusted_citation_label_rejected` |
| Numeric expression guards (`*`, `×`, `x`, `:`, etc.) | `numeric_tokens.py`; SC-R5/R6 tests; `multiplication_expression_blocks_pass` |
| Multi-source E2E truncation | `test_day9_sc_r5_acceptance.py` (`diagnostic_enrich_node`) |
| Prior R7+ closures | `test_day9_r7_acceptance.py`, `RequestCapturingGateway`, `sourceless_result_source_spoof_rejected` |

## D9-29…D9-35 demonstration trace

See `D09-SCOPE-MAP.md`, `tests/test_day9_close_acceptance.py`, and targeted `.eduvijna/pytest-targets.txt` suite.

## Persistence / compatibility (D9-33)

- **No new Day-9 tables/migrations** — taxonomy JSON + existing `OrchestrationAuditEvent` / Day-8 checkpoint tables.
- SQLite: `DATABASE_URL=sqlite:///./data/migration-d936-e1608dd.db alembic upgrade head` + `alembic check` — clean (head `20261015_0014`).
- PostgreSQL: `tests/test_postgres_compile.py` — static DDL compile only (no live Postgres on acceptance VM).

## Governance

- PR #27 **Draft**; **not merged**.
- Day 9 **ACTIVE**; `founder_approval: false`; Day 10 **LOCKED**.
- D5-DS01 / issue #16 **OPEN**; unchanged.
- No Codex.

## Founder acceptance

**Not complete.** Full regression and code review are green on `e1608dd…`, but **D9_36_FINAL_ACCEPTANCE** remains **BLOCKED** until Compose smoke is executed (or Founder explicitly accepts documented Compose risk).
