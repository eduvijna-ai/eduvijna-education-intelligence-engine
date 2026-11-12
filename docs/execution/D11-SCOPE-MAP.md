# Day 11 — scope, implementation and evidence map

**Status:** engineering targeted CI and an earlier full historical regression PASS; original NTA source proof and D11-36 Founder signoff remain pending.
**Branch:** `feature/day11-jee-main-exam-intelligence` (Draft PR #31 → `develop`).

**Arithmetic (36 tasks):** **13 PASS** · **22 PARTIAL** · **1 PENDING (D11-36)** — unchanged PASS count; repair IDs carry new test evidence where noted.

**SOURCE-AUTHORITY PENDING (11 PARTIAL; original-document investigation now authorized, curator approval NOT given):** D11-02, 03, 04, 07, 08, 11, 14, 15, 16, 21, 23 — NTA 2027 PDF/curator, official blueprint activation, authentic historical inventory.

## Task acceptance matrix

| ID | Task | Evidence | Status | Notes |
|---|---|---|---|---|
| D11-01 | Scope/provenance matrix | This file + `D11-CLOSURE-EVIDENCE.md` | PARTIAL | Full source and final-run evidence still pending |
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
| D11-14 | Historical inventory | `historical_evidence.OFFICIAL_2026_PAPER_DISCOVERY` (9 official portal links; no copied paper content) | PARTIAL | SOURCE_PENDING: PDFs, rights and item-level review |
| D11-15 | Shift tagging | `HistoricalPaperProvenance` | PARTIAL | **ON HOLD** |
| D11-16 | Historical analytics | `build_historical_analytics_report` | PARTIAL | **ON HOLD** |
| D11-17 | Soft priors | `is_mandatory_nta_quota: false` | PASS | |
| D11-18 | Typed contracts | `contracts.py` | PASS | |
| D11-19 | Math ×10 practice | `test_day11_planner.py` | PASS | |
| D11-20 | Algebra ×10 practice | `test_practice_algebra_exactly_ten_no_filler` | PASS | |
| D11-21 | Full replica | `test_day11_verified_replica_binding.py` enforces curated blueprint source pins and verified dynamic count; synthetic 75 only | PARTIAL | SOURCE_PENDING: real NTA 2027 and 75 verified questions |
| D11-22 | Section quotas | `allocator.allocate_full_replica_slots` | PASS | |
| D11-23 | Marks/response rules | `blueprint_snapshot.load_production_blueprint_snapshot` rejects missing/inconsistent official section rules; `test_official_snapshot_*` | PARTIAL | SOURCE_PENDING: actual NTA-approved rules |
| D11-24 | Bounded allocator | `allocator.py` | PASS | |
| D11-25 | Day10 distribution | `paper_distribution_bridge` and `test_explicit_distribution_targets_cannot_be_disabled_by_false_flag` | PARTIAL | Explicit targets cannot be bypassed; full Day6/source-backed quotas pending |
| D11-26 | Infeasible constraints | `IMPOSSIBLE_QUOTA`, adversarial tests, explicit-target false-flag bypass regression | PARTIAL | Full source-approved policy conflict coverage pending |
| D11-27 | LangGraph gateway | `resolve_live_generation_gateway` on `JeeMainExamIntelligenceService.plan_paper`; `test_day11_pgc02_*` | PARTIAL | Live factories w/ test inject; not live AnythingLLM |
| D11-28 | Answer validity | Persisted Day8 run readback and canonical hash/Day6 solver binding; `test_production_persist_*` | PARTIAL | General numerical solver and approved JEE evidence pending |
| D11-29 | Repair/restart | `test_day11_process_restart.py`: two independent Python workers, checkpoint resume and no new gateway calls | PARTIAL | Live provider/numerical repair evidence pending |
| D11-30 | Item provenance | Day6 lookup before APPROVED; orchestration_origin metadata | PARTIAL | |
| D11-31 | Scoring preview | `scoring.build_scoring_preview` | PASS | |
| D11-32 | Persist TestDefinition | `test_day11_process_restart.py`: stable question IDs/checksum/TestDefinition across worker processes, conflict nonmutation | PARTIAL | Production-provider/PostgreSQL evidence pending |
| D11-33 | Fixtures | `fixtures.py` | PASS | |
| D11-34 | Adversarial | `test_day11_adversarial.py` | PASS | |
| D11-35 | day11_verify + CI | `day11_verify`, targeted CI | PASS | |
| D11-36 | Founder signoff | [Full historical regression #43138935311](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/actions/runs/43138935311) PASS at `9b7806de`; [targeted #43148436965](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/actions/runs/43148436965) PASS on recent code | PENDING | Source/positive replica, final frozen-head regression and explicit Founder signoff still pending |

## Gates

| Gate | State |
|---|---|
| NTA 2027 production official pattern | **NOT_VERIFIED** (`D11-NTA-SOURCE-BLOCKER.md`) |
| Practice 10 Math / Algebra (synthetic) | PASS (fixture harness) |
| Production orchestration without fixture builder | Factory path asserted (`test_production_live_gen_uses_factory_not_fixture_builder`) |
| Full historical pytest | PASS at prior `9b7806de` SHA; newer exact-head full run pending / final gate needs recheck |
| D11-36 / merge / Day12 | **NOT AUTHORIZED** |

**Governance:** `founder_approval: false`; Day12 locked; Day4 #12 deferred; live PostgreSQL / Founder UAT NOT RUN.
