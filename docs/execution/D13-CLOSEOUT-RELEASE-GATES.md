# Day 13 closeout — release blocker register (Round 2/3)

**Baseline SHA:** `86a1fa36a95cf2d32cf1c17d89b17c667f311531`  
**Round:** 2 of 3  
**Three-round gate:** R3 → `FULL_ACCEPTED` | `MILESTONE_WITH_EXPLICIT_DEFERRALS` | `BLOCKED_STOP_AND_ESCALATE` (**no R4**)

## Distinction: targeted CI vs full historical suite

| Signal | R2 status | Meaning |
|---|---|---|
| [Targeted PR CI](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/actions/runs/45356273303) @ pre-R2 docs | **SUCCESS** | Scoped `.eduvijna/pytest-targets.txt` + Day8–13 verifiers — **does not run** full `pytest tests/` |
| Full `pytest tests/` (2395 collected) | **RED (8)** per R1; R2 attributes eight tests | See [D13-CLOSEOUT-REGRESSION-R2.md](./D13-CLOSEOUT-REGRESSION-R2.md) — **do not claim full green** |
| `compose-smoke` | **SKIPPED** (Draft) | **Not PASS** — do not mark PR Ready or claim Compose green without Founder decision |

## Critical release blockers

| # | Gate | Status | Notes |
|---|---|---|---|
| RB-01 | CUET 2026 originals + curator | **OPEN** | D13-03 `SOURCE_PENDING` |
| RB-02 | CLAT 2027 originals + rights | **OPEN** | D13-05 `SOURCE_PENDING` |
| RB-03 | F03-A / F03-B / F04-A / D13-31A | **OPEN** | 3/3 **STOP** — **Founder circuit-breaker** for any repair |
| RB-04 | Official 10/50/120 exam outputs | **OPEN** | Synthetic/reference only |
| RB-05 | D13-31 issuance + paper associations | **OPEN** | Envelope only |
| RB-06 | Day6/7/8/9/10 + AnythingLLM live | **OPEN** | **NOT_RUN** |
| RB-07 | Founder localhost UAT | **OPEN** | Runbook updated R2; **NOT_RUN** |
| RB-08 | Full historical regression | **OPEN** | Eight failures **ENVIRONMENT_SUSPECTED** in R2; suite still **RED** in acceptance terms |
| RB-09 | Compose smoke | **SKIPPED** | Draft |
| RB-10 | PostgreSQL migrate 0019–0021 | **BLOCKER + NOT_RUN** | See migration table |

## PostgreSQL / Alembic `20261124_0019` → `20261124_0021`

| Topic | Assessment |
|---|---|
| DDL string compile (`test_postgres_compile`, D31A) | **PROVEN** — not equivalent to live migrate |
| Live `alembic upgrade head` on empty PostgreSQL | **NOT_RUN** — no included disposable PG in R2 |
| `20261124_0021` `UPDATE … json_extract(metadata_json, …)` | **SOURCE-GROUNDED BLOCKER** on PostgreSQL (SQLite-only function) |
| `CHECK (synthetic_test_only = 1)` | **BLOCKER risk** on PG (prefer boolean `IS TRUE` / dialect-specific) |
| Repair | **Forbidden in closeout** — requires **Founder exception** for D13-31A migration patch |

## Four same-task circuit breakers (Founder exception to repair)

| Task | STOP review |
|---|---|
| F03-A | [comment](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/53#issuecomment-7102278457) |
| F03-B | [comment](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/53#issuecomment-7121665777) |
| F04-A | [comment](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/53#issuecomment-7122136985) |
| D13-31A | [comment](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/53#issuecomment-7125296405) |

## R2 command outcomes (bounded)

| Command | Result | Evidence |
|---|---|---|
| Eight named migration tests (default PATH) | **FAIL (8)** | [D13-R2-REGRESSION-RAW.txt](./D13-R2-REGRESSION-RAW.txt) |
| Same eight with `PATH=.venv/bin` (corroboration only) | PASS (8) | Documented in REGRESSION-R2; **not** full-suite claim |
| Full `pytest tests/` | **NOT_RUN** in R2 | R1 FAIL (8) stands for acceptance |
| `python -m app.day13_verify --json` | **PASS** | UAT keys validated in [D13-FOUNDER-LOCALHOST-UAT.md](./D13-FOUNDER-LOCALHOST-UAT.md) |
| Founder UAT | **NOT_RUN** | — |
| Live PG migrate | **NOT_RUN** | — |
| AnythingLLM live | **NOT_RUN** | — |

## Governance (unchanged)

- `founder_approval: false`; PR #53 **Draft** / unmerged; Day14 **LOCKED**
- Day11 PR #31 ON_HOLD; Day12 #35 intake **DISABLED**
- No new source activation, curator claims, or migration edits in R2

## R3 (final round)

Deliver exact-HEAD technical decision using [D13-FOUNDER-DECISION-PACKET.md](./D13-FOUNDER-DECISION-PACKET.md). **No Round 4.**