# C01 Package S scope map (S01–S08)

**Governance seed:** `ef85697ddefcd076fc2862ee77a86c7a8844919f`  
**Authorized parent (held Gate B HEAD):** `ec17e9ba5c5660235a857940d8c1c2d136e1363a`  
**Frozen develop:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Package S candidates:** **1** authorized, **1** consumed on this branch (pending push SHA)  
**Package F:** **LOCKED**  
**Deployed production/dev history:** **UNKNOWN** — external rollout **BLOCKED**  
**Independent Founder / ChatGPT exact-head review:** **REQUIRED** — no self-signoff

| Task | Outcome | Evidence (paths / symbols) |
| --- | --- | --- |
| **S01** Baseline and authority | **PASS** | Historical `0006`/`0021` revision files unchanged (`a6ca3c90…`, `b25f0192…`); 21-revision graph in `migrations/c01_revision_graph.py`; helpers/tests/CI only; no new historical revisions; Gate B PR67 frozen |
| **S02** Exact synthetic-marker constraint | **PASS** | `d13_synthetic_check_sql()` — SQLite `= 1`, PG `IS TRUE`; `D13_SYNTHETIC_MARKER_CHECK` ORM compile; tests `test_sqlite_synthetic_check_rejects_cast_weak_values`, `test_postgres_compile_synthetic_check_is_true` |
| **S03** Raw JSON + replay-state preflight | **PASS** | `strict_eligible_from_raw`, `assert_0021_preflight`; pending rows require `owner_token` (matches `durable_replay_envelope._row_integrity`); `test_sqlite_0021_preflight_accepts_in_progress_with_owner`, `test_sqlite_0021_preflight_rejects_missing_owner_on_pending` |
| **S04** Legacy / deployed state audit | **PARTIAL** | Typed `LegacyAuditReport` + graph index (`is_at_or_past_revision`); schema/CHECK verification; `test_legacy_audit_*`; **deployed** dev/prod history still **UNKNOWN/BLOCKED** |
| **S05** Owned disposable DB harness | **PASS** | `tests/c01_disposable_pg.py` allowlist; `test_disposable_pg_url_rejects_non_loopback`; PG job env in `.github/workflows/targeted-ci.yml` |
| **S06** Real migration / recovery matrix | **PARTIAL** | SQLite fresh/mixed/populated/downgrade in `tests/test_c01_migration_portability.py` (**17 passed**, 1 PG skipped locally); PG fresh empty via CI opt-in; concurrent TOCTOU / populated PG hostile matrix **NOT_RUN** locally (no loopback PG) |
| **S07** Backup / restore | **PARTIAL** | SQLite backup API `test_sqlite_backup_restore_row_hashes_match` **PASS**; PostgreSQL pg_dump/restore **NOT_RUN** (no disposable PG on agent) |
| **S08** Exact-head CI and evidence | **PARTIAL** | Ruff/mypy clean on touched modules; scoped pytest captured in `docs/execution/C01-PACKAGE-S-PYTEST-RAW.txt`; full historical regression **NOT_RUN**; Compose **SKIPPED** (Package F) |

## C01-B-R01..R05 disposition (Gate B residuals)

| Residual | Disposition |
| --- | --- |
| **C01-B-R01** CAST-truthiness synthetic CHECK | **RESOLVED** — dialect-exact CHECK (S02) |
| **C01-B-R02** Preflight owner contract vs service | **RESOLVED** — pending `owner_token` required (S03) |
| **C01-B-R03** Legacy audit false CLEAN | **PARTIAL** — fail-closed typed audit (S04); external deployed state still unknown |
| **C01-B-R04** PG disposable proof breadth | **PARTIAL** — CI path retained; extended matrix deferred to PG CI |
| **C01-B-R05** Backup evidence | **PARTIAL** — SQLite only (S07); PG backup **NOT_RUN** |

## Preserved obligations (not claimed complete)

- C01-17 PG backup/restore **NOT_RUN**
- C01-19..25 **NOT_STARTED** (Package F)
- Gate A/B budgets **exhausted**; PR **#67** held frozen
- C01 technical acceptance **pending** independent review