# Day 13 closeout — Round 2 regression attribution (eight named failures)

**Audit SHA:** `86a1fa36a95cf2d32cf1c17d89b17c667f311531`  
**Parent (R1 closeout):** `dee224b662f7185eb19464eab74093979bec0448`  
**Raw log (reviewable in repo):** [D13-R2-REGRESSION-RAW.txt](./D13-R2-REGRESSION-RAW.txt)

> **Targeted PR CI** on Draft #53 exercises `.eduvijna/pytest-targets.txt` only — **not** `pytest tests/`. A green targeted CI does **not** clear full historical regression. R1 reported **8 failures / 2395 collected**; R2 reproduces and attributes those eight tests only (no second full-suite run).

## Summary

| Metric | R1 (reported) | R2 isolated default `PATH` | R2 PATH corroboration |
|---|---|---|---|
| Eight named migration tests | FAIL (8) | **FAIL (8)** | **PASS (8)** with `PATH="$PWD/.venv/bin:$PATH"` |
| Full `pytest tests/` | FAIL (8 of 2395) | **NOT_RUN** in R2 | **NOT_RUN** in R2 |

**Interpretation:** All eight failures share one root symptom: `FileNotFoundError: … 'alembic'` because Day3/4/6 migration tests invoke a bare `alembic` subprocess (see `_run_alembic` in each test module) rather than `python -m alembic`. When the virtualenv `bin` is on `PATH` (typical after `pip install -e '.[dev]'` with an activated venv), the same eight tests **pass** in ~20s. R2 classifies the R1 full-suite red as **ENVIRONMENT_SUSPECTED** for these eight, not as confirmed migration logic regression — **without** editing tests or claiming full-suite green.

## Per-test matrix

| # | Test function | Module | R1 | R2 default PATH | Attribution | Error excerpt (sanitized) |
|---|---|---|---|---|---|---|
| 1 | `test_repaired_manual_collision_passes_actual_lifecycle_snapshot_validation` | `tests/test_day3_migration_identity_collision.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | `FileNotFoundError: … 'alembic'` at `_run_alembic` → subprocess |
| 2 | `test_partial_day3_schema_failure_rolls_back_and_can_retry` | `tests/test_day3_rework_migration.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | Same |
| 3 | `test_foreign_key_validation_failure_keeps_old_revision_and_schema` | `tests/test_day3_rework_migration.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | Same |
| 4 | `test_day4_migration_upgrade_downgrade_reupgrade_preserves_prior_data` | `tests/test_day4_migration.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | Same |
| 5 | `test_day4_failure_rolls_back_partial_schema_and_retries` | `tests/test_day4_migration.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | Same |
| 6 | `test_day6_migration_upgrade_downgrade_reupgrade` | `tests/test_day6_migration.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | Same |
| 7 | `test_day3_migration_preserves_day1_day2_records` | `tests/test_source_intelligence_migration.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | Same |
| 8 | `test_failed_day3_upgrade_keeps_previous_revision` | `tests/test_source_intelligence_migration.py` | FAIL | FAIL | **ENVIRONMENT_SUSPECTED** | Same |

## Exact R2 invocations

**Default (reproduces R1 failure mode):**

```bash
cd backend
pip install -e '.[dev]'
python -m pytest \
  tests/test_day3_migration_identity_collision.py::test_repaired_manual_collision_passes_actual_lifecycle_snapshot_validation \
  tests/test_day3_rework_migration.py::test_partial_day3_schema_failure_rolls_back_and_can_retry \
  tests/test_day3_rework_migration.py::test_foreign_key_validation_failure_keeps_old_revision_and_schema \
  tests/test_day4_migration.py::test_day4_migration_upgrade_downgrade_reupgrade_preserves_prior_data \
  tests/test_day4_migration.py::test_day4_failure_rolls_back_partial_schema_and_retries \
  tests/test_day6_migration.py::test_day6_migration_upgrade_downgrade_reupgrade \
  tests/test_source_intelligence_migration.py::test_day3_migration_preserves_day1_day2_records \
  tests/test_source_intelligence_migration.py::test_failed_day3_upgrade_keeps_previous_revision \
  -vv --tb=short
# exit code 1; 8 failed in ~0.3s
```

**Corroboration (venv CLI on PATH — read-only, does not change repo):**

```bash
cd backend
export PATH="$PWD/.venv/bin:$PATH"
python -m pytest <same eight node ids> -q --tb=no
# exit code 0; 8 passed in ~20s
```

**Environment:** Linux Cloud Agent, Python 3.12, `DATABASE_URL` per-test disposable SQLite via Alembic in `tmp_path` (no shared production DB).

## Release posture

- **Full historical suite:** remains **RED in R1 reporting**; R2 does **not** reclassify the whole suite as PASS.
- **Founder / R3:** if acceptance requires `pytest tests/` green, engineering must either run with venv `PATH` documented in CI/local docs (out of scope for R2) or align test helpers with `python -m alembic` (requires a **new** authorized change, not closeout R2).