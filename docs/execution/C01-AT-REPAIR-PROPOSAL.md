# C01 AT repair proposals (design only — no implementation)

This run is test-evidence only. Items below are **separate** Founder-authorized product repairs.

## R-AT01 — Application database guard absent

| Field | Value |
| --- | --- |
| **Failing / red evidence** | `test_at01_frozen_product_settings_guard_accepts_default_sqlite_without_opt_in` documents behavior; not a failing assertion |
| **Symbol** | `app/core/config.py` → `Settings.database_url` default |
| **Smallest change** | Add fail-closed disposable/loopback policy for non-production test harness OR document explicit production-only URL contract in settings validation |
| **Dependencies** | None on migrations |
| **Safety** | Must not widen production DB access; must not break local dev without explicit opt-in |
| **Retest** | AT01 frozen-guard test should **FAIL** until product guard exists; harness tests remain **PASS** |

## R-AT02-PG — Populated PostgreSQL `0021` chain (historical blocker)

| Field | Value |
| --- | --- |
| **Prior evidence** | Gate A/B transcripts: PG `0021` `json_extract` / strict-marker interaction |
| **Test surface** | CI `c01-migration-postgres` running `tests/test_c01_at*.py` + portability |
| **Smallest change** | **If CI fails:** dialect-specific preflight read path in `migrations/versions/20261124_0021_*` or helper — **requires separate migration repair authorization** |
| **Retest** | AT03 PG hostile + AT06 populated PG paths |

## Infrastructure (not product defects)

| Item | Status |
| --- | --- |
| Local agent without `EDUVIJNA_C01_DISPOSABLE_PG=1` | **BLOCKED** — tests correctly **SKIP**, not PASS |
| `pg_dump` / `psql` missing on agent | AT09 **SKIP** — CI service expected to provide |