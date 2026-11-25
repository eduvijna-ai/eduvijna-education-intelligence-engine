# C01 migration inventory (merged + held allocations)

**Inspection SHA:** branch `closure/c01-foundation-database-recovery` @ `1781f036d20cceae1d5fcc4b2c4e452e1e4530c7` ancestry (21 merged files on develop)  
**Alembic head (merged):** `20261124_0021`  
**Deployed application history:** **UNKNOWN** (no non-secret records of live `alembic_version` in repo; Founder evidence required)

## Merged linear graph (21 revisions)

| # | File | revision | down_revision | SHA-256 |
| --- | --- | --- | --- | --- |
| 1 | `20261001_0001_system_settings.py` | 20261001_0001 | — | `4552b1a3…c472` |
| 2 | `20261001_0002_canonical_domain.py` | 20261001_0002 | 20261001_0001 | `f9363199…b9d` |
| 3 | `20261001_0003_day1_day2_gap_closure.py` | 20261001_0003 | 20261001_0002 | `7240afd7…591` |
| 4 | `20261002_0004_day1_day2_final_blockers.py` | 20261002_0004 | 20261001_0003 | `fe7c6057…ee0` |
| 5 | `20261002_0005_source_intelligence.py` | 20261002_0005 | 20261002_0004 | `a796ffa2…10d` |
| 6 | `20261003_0006_day3_rework_closure.py` | 20261003_0006 | 20261002_0005 | `de9321ba…cee` |
| 7 | `20261003_0007_day3_legacy_compatibility.py` | 20261003_0007 | 20261003_0006 | `53cb23fb…155` |
| 8 | `20261004_0008_day4_curriculum_intelligence.py` | 20261004_0008 | 20261003_0007 | `38912418…23a` |
| 9 | `20261004_0009_framework_and_marking_scheme.py` | 20261004_0009 | 20261004_0008 | `57fb2bc9…bbc` |
| 10 | `20261007_0010_day6_education_intelligence.py` | 20261007_0010 | 20261004_0009 | `fac2f110…439` |
| 11 | `20261012_0011_day7_knowledge_intelligence.py` | 20261012_0011 | 20261007_0010 | `b219cce4…343` |
| 12 | `20261015_0012_day8_orchestration.py` | 20261015_0012 | 20261012_0011 | `dc7247fe…1ee` |
| 13 | `20261015_0013_orchestration_generation_calls.py` | 20261015_0013 | 20261015_0012 | `91e3d603…b97` |
| 14 | `20261015_0014_generation_call_status_and_lease_holder.py` | 20261015_0014 | 20261015_0013 | `e110b7a9…721` |
| 15 | `20261102_0015_curator_operator_auth.py` | 20261102_0015 | 20261015_0014 | `5d335920…7b1` |
| 16 | `20261103_0016_curator_auth_r24.py` | 20261103_0016 | 20261102_0015 | `67ccadd4…f34a` |
| 17 | `20261103_0017_curator_bootstrap_audit.py` | 20261103_0017 | 20261103_0016 | `cc0c5b07…b19` |
| 18 | `20261109_0018_curator_model_index_parity.py` | 20261109_0018 | 20261103_0017 | `02a245c1…d4a6` |
| 19 | `20261124_0019_day13_replay_envelope.py` | 20261124_0019 | 20261109_0018 | `4837db5a…59a3` |
| 20 | `20261124_0020_d13_replay_integrity_checks.py` | 20261124_0020 | 20261124_0019 | `59449cf1…a18f` |
| 21 | `20261124_0021_d13_replay_synthetic_flag.py` | 20261124_0021 | 20261124_0020 | `c90f0923…d832` |

Full hashes: `docs/execution/C01-gate-a/migration_sha256.txt` (Gate A diagnostic artifact).

## Known vs unknown applied environments

| Environment | Evidence | `0021` applied? |
| --- | --- | --- |
| CI / GitHub Actions (historical) | D13 RB-10: **NOT_RUN** live PG | UNKNOWN |
| Local SQLite engineering | C01-06: fresh upgrade **reaches 0021** on empty DB | YES (disposable trials) |
| Local disposable PostgreSQL 16.15 | C01-05: full chain **fails before 0021** at `0006` | NO |
| Dev / prod deployments | No credentials or version tables in repo | **UNKNOWN — Founder evidence required** |

## Held duplicate revision identity (C01-15)

| Held artifact | HEAD SHA | File | revision | down_revision | Notes |
| --- | --- | --- | --- | --- | --- |
| PR #57 Day15 | `b69f97bf9ee1cb08e16121f301dc20e5e5645f6f` | `20261124_0022_day15_learner_intelligence.py` | **20261124_0022** | 20261124_0021 | Learner tables DDL |
| PR #61 Day17 | `87df6a54ea8ad1c06157f894b4a4c4a1bfa3bbc1` | `20261124_0022_day17_auth_jobs.py` | **20261124_0022** | 20261124_0021 | Auth/jobs DDL — **same revision id** |
| PR #61 only downstream | `87df6a54…` | `20261125_0023_day17_job_idempotency_scope.py` | 20261125_0023 | 20261124_0022 | Uses SQLite `randomblob` in UPDATE |
| PR #61 only downstream | `87df6a54…` | `20261125_0024_refresh_session_epoch.py` | 20261125_0024 | 20261125_0023 | (not imported) |
| PR #31 Day11 | `d0f0745f6573bba0cfa93fa8eb0674cdd3b689d2` | — | — | — | **No `20261124_0022` file** at held head (head remains `0021` lineage only) |

**Import status:** No cherry-pick, merge, or checkout of held migrations on C01 branch.

## Proposed successor allocation graph (C01-16, planning only)

Assuming Gate B delivers repaired head `20261124_0021` (or successor `0021b` — **not implemented**):

```
20261124_0021 (repaired portable head on develop)
    ├── 20261125_0030_c12_identity_foundation   [proposed, unique]
    │       └── 20261125_0031_c10_learner_intel [proposed; absorbs PR57 DDL intent]
    │               └── 20261125_0032_c13_worker_jobs [proposed; absorbs PR61 DDL+0023/0024]
```

**Alternatives if historical `0021` amendment is forbidden:**

- Branch-specific revision ids with `depends_on` merge point after `0020`, plus explicit reconciliation migration reading `alembic_version` — requires Founder approval of applied-history semantics.

**Validation:** No duplicate revision ids in proposal; single head `0032`; no cycles; held `0022` ids **not** reused.