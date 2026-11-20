# Day 12 — JEE Advanced 36-task scope and evidence matrix

**Status (Issue #44 one-shot):** **0 PASS / 28 PARTIAL / 6 SOURCE_PENDING / 1 NOT_STARTED (D12-36 process).** D12-36 and CORE #35 remain NOT ACCEPTED.  
**Authoritative specification:** [Issue #33](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/33).  
**Consolidated handoff:** [Issue #44](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/44).  
**Branch:** `feature/day12-jee-advanced-intelligence` (PR #34). Day11 ON_HOLD; Day12 ACTIVE `founder_approval:false`; Day13 LOCKED.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D12-01 | Freeze scope and dependency exception | `governance.py`, `test_day12_m0_governance.py`, `D12-ONE-SHOT-CLOSURE-REPORT.md` | PARTIAL | Matrix updated; D12-36 not signed |
| D12-02 | Register brochure/syllabus | `source_registry.py`, `constants.py` (brochure alternate), `test_day12_one_shot_closure.py` | SOURCE_PENDING | No curator-approved SHA; live fetch often blocked |
| D12-03 | Register Paper1/Paper2 and keys | `source_registry.py`, `source_ingest_staging.py` | SOURCE_PENDING | Slot separation + staging; no original bytes |
| D12-04 | Curator validation lifecycle | `source_authority.py`, `source_curator_verify.py`, `test_day12_core.py` | PARTIAL | PolicyRegistry path; human curator SOURCE_PENDING |
| D12-05 | 2026 reference vs 2027 authority | `authority.py`, `test_day12_m0_governance.py` | PARTIAL | 2027 `NOT_VERIFIED`; reference blocked |
| D12-06 | Reuse ExamPack/ExamVersion | `exam_profile.py`, `test_day12_exam_profile.py` | PARTIAL | Pack bootstrap; reference blueprint unpinned |
| D12-07 | Two-paper ExamSection hierarchy | `exam_profile.py`, `test_day12_exam_profile.py` | PARTIAL | PCM + 180 min; counts unpinned |
| D12-08 | Paper-specific ExamBlueprintRule | `reference_blueprint.py`, `test_day12_reliability.py` | PARTIAL | Issue codes when rules sparse; no approved pins |
| D12-09 | Subject and syllabus catalogue | `syllabus_catalogue.py`, `test_day12_one_shot_closure.py` | SOURCE_PENDING | Requires ACTIVE syllabus revision |
| D12-10 | Curriculum/LO linkage | `syllabus_catalogue.learning_outcome_bindings_available` | PARTIAL | Fail-closed without ACTIVE syllabus |
| D12-11 | Strict scope/version guard | `scope_guard.py`, `trust_guard.py`, `test_day12_practice.py` | PARTIAL | Guards present; not full tenant matrix |
| D12-12 | Advanced reasoning-demand profile | `reasoning_profile.py` | PARTIAL | Source-neutral demo metadata only |
| D12-13 | Historical official-paper inventory | `historical_inventory.py`, `test_day12_one_shot_closure.py` | PARTIAL | Provenance rows; bytes not in repo |
| D12-14 | Question type/marking evidence tagging | `synthetic_fixtures.py` | PARTIAL | Demo types; not source-backed items |
| D12-15 | Explainable historical analytics | `historical_analytics.py`, `test_day12_assembly.py` | PARTIAL | `NOT_ANALYZABLE` default |
| D12-16 | Official constraint vs soft-prior | `constraint_precedence.py`, `test_day12_one_shot_closure.py` | PARTIAL | Precedence logic; no live teacher prefs |
| D12-17 | Typed AdvancedPaperPlanRequest/Result | `contracts.py`, planner tests | PARTIAL | Contracts; no reference replica |
| D12-18 | Exact-count subject practice | `practice_service.py`, `persisted_practice.py`, `test_day12_core.py` | PARTIAL | Day6 audit bind; synthetic pool only PASS |
| D12-19 | Exact10 Algebra | `practice_service.py`, `test_day12_core.py` | PARTIAL | Same trust order as D12-18 |
| D12-20 | Paper 1 standalone planner | `planner.py`, `test_day12_adversarial.py` | PARTIAL | Synthetic PCM; not official replica |
| D12-21 | Paper 2 standalone planner | `planner.py`, `test_day12_adversarial.py` | PARTIAL | demonstration_only |
| D12-22 | Two-paper combined simulation | `planner.py`, `synthetic_paper_assembly.py` | PARTIAL | Demo pair; not full official paper |
| D12-23 | Evidence-backed answer families | `scoring.py`, `source_attested_scoring.py` | PARTIAL | Trusted revision required |
| D12-24 | Paper/item-specific scoring rules | `source_attested_scoring.py`, `test_day12_core.py` | PARTIAL | Mandatory rubric fields |
| D12-25 | Deterministic constrained allocator | `reference_allocator.py` | PARTIAL | Reference SOURCE_PENDING |
| D12-26 | Paper cognitive/competency review | `verification_orchestration.cognitive_competency_review` | PARTIAL | Veto when weights missing |
| D12-27 | Generation/RAG | `verification_orchestration.generation_gateway_protocol` | PARTIAL | Typed Day8 port; no live LLM |
| D12-28 | Independent MCQ/multiselect | `verification_orchestration.verify_mcq_answer` | PARTIAL | REVIEW without solver evidence |
| D12-29 | Independent numerical | `verification_orchestration.verify_numerical_answer` | PARTIAL | Units/tolerance REVIEW path |
| D12-30 | STEM integrity | `verification_orchestration.verify_stem_assets` | PARTIAL | LaTeX/alt-text REVIEW |
| D12-31 | Bounded repairs/dedup | `verification_orchestration.bounded_repair_allowed` | PARTIAL | Repair budget gate |
| D12-32 | Persist/replay two-paper pair | `paper_pair_persistence.py`, `test_day12_core.py` | PARTIAL | Cross-process demo; PG NOT_RUN |
| D12-33 | Synthetic reference fixtures | `synthetic_fixtures.py`, assembly/adversarial tests | PARTIAL | `demonstration_only` |
| D12-34 | Adversarial acceptance suite | `tests/test_day12_*.py` (11 modules) | PARTIAL | Issue #44 vectors added; not every #33 row E2E |
| D12-35 | Day12 verifier and CI gates | `day12_verify.py`, `.eduvijna/pytest-targets.txt` | PARTIAL | Full historical pytest recorded in closure report |
| D12-36 | Independent review and Founder signoff | `D12-ONE-SHOT-CLOSURE-REPORT.md` | NOT_STARTED | Awaiting Chief Architect + Founder |

## Acceptance rules
- Synthetic demonstration must never be claimed as curator-approved 2026 reference or 2027 official replica.
- `reference_2026_curator_approved` and `official_2027_approved` remain false until real evidence exists.
- Full historical `pytest tests/` — run on one-shot candidate; see `D12-ONE-SHOT-CLOSURE-REPORT.md` for outcome.
- D12-36 remains PENDING until separate Founder signoff.