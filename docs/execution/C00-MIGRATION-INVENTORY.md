# C00-08 — Alembic migration inventory

**Merged develop HEAD:** `8b71aa03bcff21f021f43ea430935edf14070f68`  
**Held Day 17 HEAD:** `87df6a54ea8ad1c06157f894b4a4c4a1bfa3bbc1` (not merged)

## Merged linear graph (21 revisions)

| File | revision id | down_revision |
| --- | --- | --- |
| `20261001_0001_system_settings.py` | 20261001_0001 | None |
| `20261001_0002_canonical_domain.py` | 20261001_0002 | 20261001_0001 |
| `20261001_0003_day1_day2_gap_closure.py` | 20261001_0003 | 20261001_0002 |
| `20261002_0004_day1_day2_final_blockers.py` | 20261002_0004 | 20261001_0003 |
| `20261002_0005_source_intelligence.py` | 20261002_0005 | 20261002_0004 |
| `20261003_0006_day3_rework_closure.py` | 20261003_0006 | 20261002_0005 |
| `20261003_0007_day3_legacy_compatibility.py` | 20261003_0007 | 20261003_0006 |
| `20261004_0008_day4_curriculum_intelligence.py` | 20261004_0008 | 20261003_0007 |
| `20261004_0009_framework_and_marking_scheme.py` | 20261004_0009 | 20261004_0008 |
| `20261007_0010_day6_education_intelligence.py` | 20261007_0010 | 20261004_0009 |
| `20261012_0011_day7_knowledge_intelligence.py` | 20261012_0011 | 20261007_0010 |
| `20261015_0012_day8_orchestration.py` | 20261015_0012 | 20261012_0011 |
| `20261015_0013_orchestration_generation_calls.py` | 20261015_0013 | 20261015_0012 |
| `20261015_0014_generation_call_status_and_lease_holder.py` | 20261015_0014 | 20261015_0013 |
| `20261102_0015_curator_operator_auth.py` | 20261102_0015 | 20261015_0014 |
| `20261103_0016_curator_auth_r24.py` | 20261103_0016 | 20261102_0015 |
| `20261103_0017_curator_bootstrap_audit.py` | 20261103_0017 | 20261103_0016 |
| `20261109_0018_curator_model_index_parity.py` | 20261109_0018 | 20261103_0017 |
| `20261124_0019_day13_replay_envelope.py` | 20261124_0019 | 20261109_0018 |
| `20261124_0020_d13_replay_integrity_checks.py` | 20261124_0020 | 20261124_0019 |
| `20261124_0021_d13_replay_synthetic_flag.py` | 20261124_0021 | 20261124_0020 |

**Merged head:** `20261124_0021`

## Held-only revisions (PR #61)

| File | revision id | down_revision |
| --- | --- | --- |
| `20261124_0022_day17_auth_jobs.py` | 20261124_0022 | 20261124_0021 |
| `20261125_0023_day17_job_idempotency_scope.py` | 20261125_0023 | 20261124_0022 |
| `20261125_0024_refresh_session_epoch.py` | 20261125_0024 | 20261125_0023 |

**Collision note:** Held branch extends the same numeric sequence from `0021`. Integrating held Day 15/17 without C01 reconciliation risks **multiple heads** or renumbering conflicts — assigned to **C01**, not executed in C00.

## PG0021 / live PostgreSQL

| Evidence type | Status |
| --- | --- |
| SQLite upgrade through 0021 on develop | NOT_RUN this audit (static inventory only) |
| Live PostgreSQL upgrade through 0021 | **BLOCKER_DEFERRED_NOT_PASSED** per execution-state Days 13/18 |
| PG0021 root cause | **UNKNOWN** — documented failure references exist; no isolated fresh/populated PG reproduction in this audit |
| Proposed C01 investigation | Reproduce on fresh + populated PG; capture Alembic error log; compare batch_alter vs PG DDL for `d13_replay_reservations` |

## Safe recovery mapping (proposal only)

1. **C01:** establish single authoritative head before any new migration auth.  
2. **C01:** reconcile held `0022–0024` numbering/dependencies against Day 15 held migrations (if any) before integration planning.  
3. No skip/rewrite of applied history without Founder-approved strategy.