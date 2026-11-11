# Day 11 — scope, implementation and evidence map

**Status:** PGC-01 production generation handback (factory path + validation gates), **not** D11-36 signoff.
**Branch:** `feature/day11-jee-main-exam-intelligence` (Draft PR #31 → `develop`).

**Arithmetic (36 tasks):** **13 PASS** · **22 PARTIAL** · **1 PENDING (D11-36)** — unchanged PASS count; repair IDs carry new test evidence where noted.

**HOLD (11 PARTIAL, no external-source work this handoff):** D11-02, 03, 04, 07, 08, 11, 14, 15, 16, 21, 23 — NTA 2027 PDF/curator, official blueprint activation, authentic historical inventory.

## Task acceptance matrix

| ID | Task | Evidence | Status | Notes |
|---|---|---|---|---|
| D11-01 | Scope/provenance matrix | This file + per-row test IDs | PARTIAL | Matrix is source of truth |
| D11-02 | 2027 bulletin | `source_authority.register_nta_2027_candidate_sources` | PARTIAL | **ON HOLD** — curator PDF |
| D11-03 | 2027 syllabus | same | PARTIAL | **ON HOLD** |
| D11-04 | Official extraction workflow | `source_authority` + `test_day11_trust.py` | PARTIAL | **ON HOLD** — production fail-closed |
| D11-05 | ExamPack/ExamVersion | `exam_catalogue.ensure_jee_main_exam_catalogue` | PASS | |
| D11-06 | Section hierarchy | `exam_catalogue._ensure_paper1_sections_and_rules` | PASS | |
| D11-07 | ExamBlueprintRule | `exam_catalogue` | PARTIAL | **ON HOLD** — verified_official |
| D11-08 | Amendments/drift | `source_authority.detect_source_drift` | PARTIAL | **ON HOLD** |
| D11-09 | Referential/trust checks | `verify_production_day6_binding`, PGC-01 Day6-before-APPROVED in `persist_draft_items`; `test_day11_pgc01_*` | PARTIAL | Engineering: production persist gate |
| D11-10 | Subject catalogue | `syllabus_mapping.validate_subject_code` | PASS | |
| D11-11 | Topic mapping | `OFFICIAL_JEE_MAIN_2027_TOPICS` seed | PARTIAL | **ON HOLD** — NTA ingest |
| D11-12 | Curriculum nodes | `curriculum_linkage.curriculum_link_status` fail-closed | PARTIAL | **ON HOLD** pending NTA |
| D11-13 | Syllabus guard | `syllabus_mapping.syllabus_guard_passes` | PARTIAL | Catalogue-only guard |
| D11-14 | Historical inventory | `historical_evidence` synthetic | PARTIAL | **ON HOLD** |
| D11-15 | Shift tagging | `HistoricalPaperProvenance` | PARTIAL | **ON HOLD** |
| D11-16 | Historical analytics | `build_historical_analytics_report` | PARTIAL | **ON HOLD** |
| D11-17 | Soft priors | `is_mandatory_nta_quota: false` | PASS | |
| D11-18 | Typed contracts | `contracts.py` | PASS | |
| D11-19 | Math ×10 practice | `test_day11_planner.py` | PASS | |
| D11-20 | Algebra ×10 practice | `test_practice_algebra_exactly_ten_no_filler` | PASS | |
| D11-21 | Full replica | synthetic 75; production FAIL | PARTIAL | **ON HOLD** — NTA |
| D11-22 | Section quotas | `allocator.allocate_full_replica_slots` | PASS | |
| D11-23 | Marks/response rules | `blueprint_snapshot` | PARTIAL | **ON HOLD** |
| D11-24 | Bounded allocator | `allocator.py` | PASS | |
| D11-25 | Day10 distribution | `paper_distribution_bridge` + `test_day11_r2.py`, `test_day11_focused_repair.py` | PARTIAL | Mandatory policy without targets → FAIL |
| D11-26 | Infeasible constraints | `IMPOSSIBLE_QUOTA` + adversarial/focused tests | PARTIAL | |
| D11-27 | LangGraph gateway | `acquire_orchestration_service` + `build_jee_production_orchestration_request`; `test_day11_pgc01_production_generation.py` | PARTIAL | Live factories w/ test inject; not live AnythingLLM |
| D11-28 | Answer validity | Day6 binding + 4-option MCQ + solver disagree gate; PGC-01 tests | PARTIAL | |
| D11-29 | Repair/restart | File-backed durable HITL resume `test_durable_hitl_resume_*` | PARTIAL | No process-level worker restart |
| D11-30 | Item provenance | Day6 lookup before APPROVED; orchestration_origin metadata | PARTIAL | |
| D11-31 | Scoring preview | `scoring.build_scoring_preview` | PASS | |
| D11-32 | Persist TestDefinition | `test_persistence_*`, durable HITL `test_durable_hitl_resume_*`; gateway call equality on resume | PARTIAL | File SQLite checkpoint; no process restart |
| D11-33 | Fixtures | `fixtures.py` | PASS | |
| D11-34 | Adversarial | `test_day11_adversarial.py` | PASS | |
| D11-35 | day11_verify + CI | `day11_verify`, targeted CI | PASS | |
| D11-36 | Founder signoff | — | PENDING | Full historical pytest NOT RUN |

## Gates

| Gate | State |
|---|---|
| NTA 2027 production official pattern | **NOT_VERIFIED** (`D11-NTA-SOURCE-BLOCKER.md`) |
| Practice 10 Math / Algebra (synthetic) | PASS (fixture harness) |
| Production orchestration without fixture builder | Factory path asserted (`test_production_live_gen_uses_factory_not_fixture_builder`) |
| D11-36 / merge / Day12 | **NOT AUTHORIZED** |

**Governance:** `founder_approval: false`; Day12 locked; Day4 #12 deferred; live PostgreSQL / Founder UAT NOT RUN.
