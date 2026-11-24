# Day 16 — Adaptive Remediation 36-task scope and evidence matrix

**Status:** **0 PASS / 35 PARTIAL / 0 SOURCE_PENDING / 1 NOT_STARTED = 36 rows.** D16-36 pending Founder signoff.  
**Authoritative specification:** [Issue #58](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/58).  
**Branch:** `feature/day16-adaptive-remediation` (PR #59). Day15 ON_HOLD; Day16 ACTIVE `founder_approval:false`; Day17 LOCKED.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D16-01 | Scope and dependency freeze | `governance.py`, `D16-SCOPE-MAP.md`, `test_day16_m0_governance.py` | PARTIAL | Founder exact-HEAD review pending |
| D16-02 | Independent adaptive input contract | `contracts.py`, `test_day16_core.py` | PARTIAL | No Day15 ORM dependency |
| D16-03 | Trust and runtime containment | `containment.py`, `production_gate.py`, `test_day16_adversarial.py` | PARTIAL | Production NOT_READY always |
| D16-04 | Synthetic fixture catalogue | `synthetic_catalogue.py`, `synthetic_graph.py`, `test_day16_core.py` | PARTIAL | Non-actionable internal only |
| D16-05 | Evidence normalization | `evidence.py`, `test_day16_evidence.py` | PARTIAL | Cross-version/stale rejection |
| D16-06 | Curriculum and examination scope | `contracts.py`, `test_day16_core.py` | PARTIAL | No official replica claim |
| D16-07 | Adaptive policy registry | `policy.py`, `test_day16_policy.py` | PARTIAL | No psychometric claims |
| D16-08 | Cold-start assessment needs | `evidence.py`, `policy.py`, `test_day16_policy.py` | PARTIAL | UNKNOWN not weakness |
| D16-09 | Target-concept prioritization | `policy.py`, `test_day16_policy.py` | PARTIAL | Deterministic tie-break |
| D16-10 | Correction-pattern targeting | `policy.py`, `test_day16_policy.py` | PARTIAL | Recurrent vs single |
| D16-11 | Prerequisite graph integration | `prerequisite_plan.py`, Day10 `audit.py`, `test_day16_graph.py` | PARTIAL | No DB loader in D16 |
| D16-12 | Graph validation | `prerequisite_plan.graph_ready`, `test_day16_graph.py` | PARTIAL | Cycle/missing node tests |
| D16-13 | Root-cause hypothesis ranking | `policy.map_strategy`, `test_day16_graph.py` | PARTIAL | No single-error diagnosis |
| D16-14 | Prerequisite remediation ordering | `foundation_first_order`, `test_day16_graph.py` | PARTIAL | Bounded budget |
| D16-15 | Remediation strategy selection | `policy.py`, `test_day16_graph.py` | PARTIAL | Unsupported -> assessment |
| D16-16 | Cognitive progression | `practice_plan.py`, `enums.py`, `test_day16_practice.py` | PARTIAL | Synthetic fixtures only |
| D16-17 | Difficulty progression | `practice_plan.py`, `test_day16_practice.py` | PARTIAL | No calibrated ability |
| D16-18 | Practice allocation exact count | `practice_plan.py`, `test_day16_practice.py` | PARTIAL | Infeasible -> NOT_READY |
| D16-19 | Targeted practice blueprint | `contracts.PracticeStageBlueprint`, `test_day16_practice.py` | PARTIAL | Plan-only |
| D16-20 | Question selection constraints | `synthetic_catalogue.py`, `test_day16_practice.py` | PARTIAL | Internal catalogue only |
| D16-21 | Generation integration contract | `integration_contracts.py`, `test_day16_core.py` | PARTIAL | CONTRACT_ONLY |
| D16-22 | Validation and delivery gate | `production_gate.py`, `service.py`, `test_day16_core.py` | PARTIAL | delivered/validated zero |
| D16-23 | Remediation explanation | `service.py`, `test_day16_core.py` | PARTIAL | Non-actionable wording |
| D16-24 | Foundation practice stage | `synthetic_catalogue.py`, `test_day16_adaptation.py` | PARTIAL | Friction fixture foundation |
| D16-25 | Application practice stage | `synthetic_catalogue.py`, `test_day16_adaptation.py` | PARTIAL | Synthetic application stage |
| D16-26 | Target reassessment stage | `synthetic_catalogue.py`, `test_day16_adaptation.py` | PARTIAL | Fresh retest items |
| D16-27 | Adaptation decision rules | `adaptation.py`, `test_day16_adaptation.py` | PARTIAL | No mastery on completion |
| D16-28 | Repetition, spacing, preferences | `adaptation.py`, `teacher_policy.py`, `test_day16_adaptation.py` | PARTIAL | No real schedule |
| D16-29 | Teacher/institution policy boundary | `teacher_policy.py`, `test_day16_adversarial.py` | PARTIAL | Cannot weaken gates |
| D16-30 | Plan versioning and replay | `fingerprint.py`, `test_day16_adversarial.py` | PARTIAL | No persistence claim |
| D16-31 | Read/output privacy contract | `production_gate.py`, `contracts.py`, `test_day16_adversarial.py` | PARTIAL | No PII in outputs |
| D16-32 | Dependency closure register | `dependency_closure.py`, `test_day16_m0_governance.py` | PARTIAL | Day15 blocked explicit |
| D16-33 | Adversarial and regression tests | `tests/test_day16_*.py` | PARTIAL | Full matrix not every vector |
| D16-34 | Founder verifier | `day16_verify.py`, `test_day16_verify_sha.py` | PARTIAL | CI hook on PR head |
| D16-35 | CI and compatibility | `.eduvijna/pytest-targets.txt`, targeted-ci | PARTIAL | Full regression deferred |
| D16-36 | Independent acceptance and stop | This matrix | NOT_STARTED | Chief Architect + Founder |

## Acceptance rules
- Synthetic diagnostics must never imply real learner remediation, issuance, scheduling or persistence.
- Day15 modules, ORM, schema and migration 0022 must not be imported.
- Day14 `ACADEMIC_VALIDATION_DISABLED` and `ISSUANCE_DISABLED` must remain true.
- D16-36 remains NOT_STARTED until separate Founder signoff.