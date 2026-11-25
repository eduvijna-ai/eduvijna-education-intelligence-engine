# C00-08 — Merged and held migration inventory (candidate 3/3)

Frozen develop baseline: `8b71aa03bcff21f021f43ea430935edf14070f68` (head `20261124_0021`).

## Merged linear chain (21 revisions)

| Order | File | revision | down_revision |
| --- | --- | --- | --- |
| 1 | `20261001_0001_system_settings.py` | 20261001_0001 | — |
| 2 | `20261001_0002_canonical_domain.py` | 20261001_0002 | 20261001_0001 |
| 3 | `20261001_0003_day1_day2_gap_closure.py` | 20261001_0003 | 20261001_0002 |
| 4 | `20261002_0004_day1_day2_final_blockers.py` | 20261002_0004 | 20261001_0003 |
| 5 | `20261002_0005_source_intelligence.py` | 20261002_0005 | 20261002_0004 |
| 6 | `20261003_0006_day3_rework_closure.py` | 20261003_0006 | 20261002_0005 |
| 7 | `20261003_0007_day3_legacy_compatibility.py` | 20261003_0007 | 20261003_0006 |
| 8 | `20261004_0008_day4_curriculum_intelligence.py` | 20261004_0008 | 20261003_0007 |
| 9 | `20261004_0009_framework_and_marking_scheme.py` | 20261004_0009 | 20261004_0008 |
| 10 | `20261007_0010_day6_education_intelligence.py` | 20261007_0010 | 20261004_0009 |
| 11 | `20261012_0011_day7_knowledge_intelligence.py` | 20261012_0011 | 20261007_0010 |
| 12 | `20261015_0012_day8_orchestration.py` | 20261015_0012 | 20261012_0011 |
| 13 | `20261015_0013_orchestration_generation_calls.py` | 20261015_0013 | 20261015_0012 |
| 14 | `20261015_0014_generation_call_status_and_lease_holder.py` | 20261015_0014 | 20261015_0013 |
| 15 | `20261102_0015_curator_operator_auth.py` | 20261102_0015 | 20261015_0014 |
| 16 | `20261103_0016_curator_auth_r24.py` | 20261103_0016 | 20261102_0015 |
| 17 | `20261103_0017_curator_bootstrap_audit.py` | 20261103_0017 | 20261103_0016 |
| 18 | `20261109_0018_curator_model_index_parity.py` | 20261109_0018 | 20261103_0017 |
| 19 | `20261124_0019_day13_replay_envelope.py` | 20261124_0019 | 20261109_0018 |
| 20 | `20261124_0020_d13_replay_integrity_checks.py` | 20261124_0020 | 20261124_0019 |
| 21 | `20261124_0021_d13_replay_synthetic_flag.py` | 20261124_0021 | 20261124_0020 |

## PG0021 / upgrade evidence

| Item | Status |
| --- | --- |
| Live PostgreSQL Alembic upgrade to `0021` | **UNKNOWN** — no reproducible artifact in repo at audit time |
| Failure record cited in execution-state / D13 reviews | **NOT_VERIFIED** — referenced in C01 planning only |
| SQLite head at frozen baseline | Files present; **NOT_RUN** migration execution this audit |

## Held duplicate revision identity (preserved from candidate 2)

| Held PR | SHA | File | revision | down_revision |
| --- | --- | --- | --- | --- |
| #57 | `b69f97bf` | `backend/migrations/versions/20261124_0022_day15_learner_intelligence.py` | **20261124_0022** | 20261124_0021 |
| #61 | `87df6a54` | `backend/migrations/versions/20261124_0022_day17_auth_jobs.py` | **20261124_0022** | 20261124_0021 |

Downstream on held PR #61 only (not merged): `20261125_0023_day17_job_idempotency_scope.py` → `20261125_0024_refresh_session_epoch.py`.

C01 proposal: reconcile duplicate `0022` before any held merge — planning only; no execution in C00.