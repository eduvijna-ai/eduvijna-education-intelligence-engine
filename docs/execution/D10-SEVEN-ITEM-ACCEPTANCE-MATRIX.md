# Day 10 — Seven-item consolidated acceptance matrix

**Authorization:** Founder 2026-11-10 (“ok, proceed”) for **D10-12 / 19 / 22 / 28 / 29 / 32 / 33** only.  
**Anchor tests:** `backend/tests/test_day10_seven_item_acceptance.py` (6 integrated proofs) plus cited legacy tests.

## D10-12 — Mapping catalogue / registry

| Subcriterion | Code path | Test | Result | Status |
|--------------|-----------|------|--------|--------|
| Enumerate configured mappings + version/lineage | `mapping_registry.mapping_catalogue`, `data/root_cause_mapping_v1.json` | `test_d10_12_mapping_catalogue_overlay_and_unknown_misconception` | 2 codes, `synthetic:true`, version `root-cause-mapping@v1` | **IMPLEMENTED** |
| Registry → signed overlay → resolver | `mapping_authority.apply_mapping_authority_overlay` | same + `test_day10_r11_trust.py`, `test_day10_r17_trust.py` | Sourced overlay non-synthetic in production | **IMPLEMENTED** |
| Unknown misconception never invents concept | `RootCauseIntelligenceService.analyze` | `test_d10_12_*` | `FAIL` + `UNKNOWN_MISCONCEPTION`, zero hypotheses | **IMPLEMENTED** |
| Forged/inactive claim negatives | `mapping_claim_authority.approve_root_cause_mapping_claim` | `test_day10_r17_trust.py`, `test_day10_r27_trust.py`, `test_day10_r32_*` | Raises / non-PASS | **IMPLEMENTED** |

**Coverage note:** Catalogue lists only shipped JSON mappings (2 synthetic demo entries). No fabricated official curricula.

## D10-19 — LO / competency / curriculum alignment

| Subcriterion | Code path | Test | Result | Status |
|--------------|-----------|------|--------|--------|
| Persisted Day6 binding positive | `day6_binding_verify.verify_production_day6_binding` | `test_d10_19_lo_competency_curriculum_and_day6_blocking_matrix` | Pass aligned LO/tenant | **IMPLEMENTED** |
| Wrong LO / foreign institution | same | same | Fail `learning_outcome_ids` / `institution_id` | **IMPLEMENTED** |
| Day6 blocking never RC PASS | `preflight.run_root_cause_preflight` | same | `DAY6_BLOCKING`, non-PASS | **IMPLEMENTED** |
| Extended matrix (grade/medium/graph) | `trust_verify`, `graph_verify` | `test_day10_r19_trust.py`, `test_day10_r8_trust.py` | Fail-closed | **IMPLEMENTED** |

## D10-22 — Day8/9 integration + HITL

| Subcriterion | Code path | Test | Result | Status |
|--------------|-----------|------|--------|--------|
| Compiled orchestration + root-cause PASS + hypotheses | `orchestration/service.py`, `nodes/root_cause.py` | `test_d10_22_orchestration_interrupt_resume_identical_root_cause` | COMPLETED, ≥1 PASS hypothesis | **IMPLEMENTED** |
| HITL interrupt → resume identical outcome | `OrchestrationService.run` + checkpoint | same | Replay same `run_id`, no extra gateway/audit | **IMPLEMENTED** |
| Day6/Day9 blocking / correct-option paths | orchestration validators | `test_day10_r21_trust.py`, `test_day10_r12_trust.py` | Non-PASS / veto sibling | **IMPLEMENTED** |

## D10-28 — Mandatory target policy precedence

| Subcriterion | Code path | Test | Result | Status |
|--------------|-----------|------|--------|--------|
| Board + institution + teacher merge | `mandatory_policy_resolver.merge_scoped_mandatory_policy_payload` | `test_d10_28_29_three_tier_mandatory_and_quota_reconcile` | Remember count 2, apply range tightened | **IMPLEMENTED** |
| Board beats weaker institution | `mandatory_policy_claim_authority` | `test_day10_r27_trust.py::test_board_remember_mandatory_precedence_over_weaker_institution_rule` | Weaken rejected at approval | **IMPLEMENTED** |
| Teacher cannot weaken board apply% | resolver + claim auth | `test_day10_r28_trust.py::test_teacher_weaken_rule_does_not_reduce_board_apply_mandatory` | Non-PASS / no drop | **IMPLEMENTED** |
| Signed/revoked/forged policy negatives | claim + resolver | `test_day10_r32–r35_trust.py` | Typed errors / fail-closed | **IMPLEMENTED** |

## D10-29 — Deterministic quotas

| Subcriterion | Code path | Test | Result | Status |
|--------------|-----------|------|--------|--------|
| 33/33/34 largest remainder | `evaluator.reconcile_exact_counts` | `test_d10_28_29_*`, `test_day10_r10_trust.py` | 1/1/1 @ N=3 | **IMPLEMENTED** |
| Fractional competency 50/50 | `evaluator._evaluate_dimension_targets` | `test_day10_r12_trust.py` | PASS 0.5/0.5 | **IMPLEMENTED** |
| Mandatory exact_count conflicts | `target_policy_registry.merge_mandatory_*` | `test_day10_r12_trust.py`, `test_day10_r18_trust.py` | Typed non-PASS | **IMPLEMENTED** |
| Mark-weighted vs count divergence | evaluator mark-weighted | `test_day10_r28_trust.py`, `test_day10_r31_trust.py` | Separate reporting | **IMPLEMENTED** |

## D10-32 — Adversarial catalogue

| Scenario class | Primary existing test | Seven-item smoke |
|----------------|----------------------|------------------|
| Foreign tenant graph | `test_day10_r8_trust.py` | `test_d10_32_adversarial_production_path_smoke` |
| Forged OFFICIAL edge / no allowlist | `test_day10_adversarial.py` | same |
| Forged mapping claim | `test_day10_r17_trust.py` | same |
| Cycle / contradictory edges | `test_day10_graph.py` | (referenced) |
| Cross-tenant audit / Day9 scope | `test_day10_r14_trust.py`, `test_day10_r8_trust.py` | cited |
| Mandatory revoke/retire/forgery | `test_day10_r33–r35_trust.py` | cited |

**Status:** **IMPLEMENTED** — auditable matrix with production-path exercises; not exhaustive permutation of all exam patterns.

## D10-33 — Batch, replay, persistence

| Subcriterion | Code path | Test | Result | Status |
|--------------|-----------|------|--------|--------|
| Paper audit idempotency (same Day6 identity) | `paper_distribution/audit.persist_paper_distribution_audit` | `test_d10_33_paper_replay_idempotent_under_same_day6_binding_set` | Same audit `run_id` on replay | **IMPLEMENTED** |
| Orchestration HITL replay | `OrchestrationService` + checkpoint | `test_d10_22_*`, `test_day10_r21_trust.py`, `test_day10_r15_trust.py` | No duplicate gateway/audits | **IMPLEMENTED** |
| SQLite Alembic upgrade head | migrations | `test_day10_r14_trust.py::test_day10_sqlite_alembic_upgrade_head` | Head `20261109_0018` | **IMPLEMENTED** |
| PostgreSQL DDL compile | SQLAlchemy compile | `test_day10_r14_trust.py::test_day10_postgresql_ddl_compiles` | Compiles | **IMPLEMENTED** |
| Live PostgreSQL | — | **NOT RUN** | Per frozen spec | **DEFERRED** |

## Governance

- **D10-36:** PENDING Founder/Chief Architect signoff (not self-approved).
- **founder_approval:** unchanged `false`; Day **11 LOCKED**.
