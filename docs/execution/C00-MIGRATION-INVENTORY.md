# C00-08 — Alembic migration inventory (candidate 2/3)

**Merged develop HEAD:** `8b71aa03bcff21f021f43ea430935edf14070f68`

## Merged head

`20261124_0021` (`20261124_0021_d13_replay_synthetic_flag.py`) — linear chain of 21 revisions documented in candidate 1; unchanged on develop.

## Critical duplicate revision identity (verified read-only)

Both held branches declare **the same** Alembic revision id and parent:

| Branch | File | `revision` | `down_revision` |
| --- | --- | --- | --- |
| PR #57 `b69f97bf` | `backend/migrations/versions/20261124_0022_day15_learner_intelligence.py` | **20261124_0022** | **20261124_0021** |
| PR #61 `87df6a54` | `backend/migrations/versions/20261124_0022_day17_auth_jobs.py` | **20261124_0022** | **20261124_0021** |

This is not a hypothetical numbering collision: **two different DDL files share one revision id**. Only one can be applied on a single database history.

### PR #61 continuation (held only)

| File | revision | down_revision |
| --- | --- | --- |
| `20261125_0023_day17_job_idempotency_scope.py` | 20261125_0023 | 20261124_0022 |
| `20261125_0024_refresh_session_epoch.py` | 20261125_0024 | 20261125_0023 |

## PG0021 / live PostgreSQL

| Evidence | Status |
| --- | --- |
| execution-state Days 13/18 | `BLOCKER_DEFERRED_NOT_PASSED` |
| Isolated fresh PG upgrade | **NOT_RUN** (C00 audit-only) |
| Recorded failure artifact | execution-state reference only; root cause **UNKNOWN** pending C01 |
| SQLite DDL compile tests in repo | exist at baseline; **NOT_EXECUTED** this audit |

C01 must reproduce on fresh + populated PostgreSQL before any integration merge of held PR57/61.