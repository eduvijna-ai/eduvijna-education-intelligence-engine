# C01 AT01–AT10 scope map (Issue #70)

**Governance seed (pre-evidence):** `a1ca50c90877806ab3f7d72068982f88f98aa22f`  
**Authorized Package S product baseline:** `e7ce396aa088dab2cbdfebadab1ae0d4efaaef67`  
**Frozen develop:** `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7`  
**Held PR67:** `ec17e9ba5c5660235a857940d8c1c2d136e1363a`  
**Held PR69:** `e7ce396aa088dab2cbdfebadab1ae0d4efaaef67`  
**Acceptance run budget:** 1/1 (this delivery)  
**Product `implementation_authorized`:** false throughout  
**Independent exact-head review:** REQUIRED — no self-signoff

| AT | Issue #70 contract | Named tests (module) | Dialect | Local agent result | Evidence |
| --- | --- | --- | --- | --- | --- |
| **AT01** | Disposable ownership / opt-in URL / cleanup | `test_c01_at01_disposable_harness.py` | SQLite **PASS**; PG **NOT_RUN** (no opt-in on agent) | Harness **PASS** (6/7); `test_at01_pg_creates_exclusively_owned_empty_database` **SKIPPED** | `docs/execution/C01-AT-PYTEST-RAW.txt`; frozen `Settings.database_url` **RED** (no disposable guard) |
| **AT02** | Exact synthetic + `source_revisions` lifecycle | `test_c01_at02_exact_constraints.py` | SQLite **PASS**; PG live CHECK **NOT_RUN** | **PASS** (4/5); PG synthetic probe **SKIPPED** | Same raw log; migrated vs ORM-labeled tests separated |
| **AT03** | Unmodified 0020→0021 preflight | `test_c01_at03_0021_preflight.py` | SQLite **PASS** | **PASS** (4/4) | Digest-stable abort on hostile fixture |
| **AT04** | `audit_legacy_0021_state` red cases | `test_c01_at04_legacy_audit.py` | SQLite **PASS** | **PASS** (6/6) | Typed statuses; no uncaught DB errors |
| **AT05** | Concurrency / lock busy | `test_c01_at05_concurrency.py` | SQLite **PASS** | **PASS** (2/2) | `sqlite3.OperationalError: database is locked` observed |
| **AT06** | Migration path matrix | `test_c01_at06_migration_paths.py` | SQLite **PASS** | **PASS** (3/3) | Fresh head + 0018→0021 + 0005→0006 |
| **AT07** | Downgrade/re-upgrade / FK restore | `test_c01_at07_atomic_recovery.py` | SQLite **PASS** | **PASS** (2/2) | `alembic check` after re-upgrade |
| **AT08** | Populated SQLite backup API | `test_c01_at08_sqlite_backup.py` | SQLite **PASS** | **PASS** (1/1) | Nonempty org/inst/source/replay before backup |
| **AT09** | pg_dump/restore | `test_c01_at09_pg_backup.py` | PG **NOT_RUN** | **SKIPPED** (no PG opt-in / tools) | CI disposable PG job is authoritative for live path |
| **AT10** | CI / exact-head / collection | `test_c01_at10_ci_evidence.py` + workflows | Meta **PASS** | **PASS** (4/4); full historical regression **NOT_RUN** | `.github/workflows/targeted-ci.yml`; `C01-AT-junit.xml` |

## Harness safety vs frozen product guard

| Layer | Observation |
| --- | --- |
| **New AT01 harness** (`tests/c01_disposable_pg.py`, `tests/c01_at_support.py`) | Rejects remote host, query/fragment, absent opt-in, `DATABASE_URL` alias |
| **Frozen product** (`app/core/config.py` `Settings.database_url`) | Accepts default `sqlite:///./data/eduvijna.db` with **no** disposable-database policy — recorded in `test_at01_frozen_product_settings_guard_accepts_default_sqlite_without_opt_in` |

## S-R01..05 / C01-B-R residual disposition (this run only)

| Residual | Disposition |
| --- | --- |
| **S-R01** Legacy/deployed unknown | **UNCHANGED** — audit tests exercised; no production claim |
| **S-R02** Disposable harness | **PARTIAL** — harness **PASS** SQLite; PG breadth deferred to CI |
| **S-R03** Migration/preflight | **PARTIAL** — SQLite **PASS**; PG populated hostile 0021 **PENDING CI** (historical blocker may **FAIL**) |
| **S-R04** Backup | **PARTIAL** — SQLite populated **PASS**; PG dump **PENDING CI** |
| **S-R05** CI evidence | **PARTIAL** — scoped job updated; await GitHub run on push SHA |
| **C01-B-R01..05** | Prior Package S dispositions preserved; no product repair in this run |