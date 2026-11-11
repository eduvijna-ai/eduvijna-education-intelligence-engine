# Day 11 — scope, implementation and evidence map

**Status:** R2 final bounded pass (CI + D11-25/27 boundary), **not** Founder D11-36 signoff.
**Founder authorization:** 2026-11-10 — “Approved to start cursor handoff.”
**Branch:** `feature/day11-jee-main-exam-intelligence` (Draft PR #31 → `develop`).

- Canonical specification: `docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md` and [Issue #30](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/30).
- **NTA authority gate:** candidate 2027 bulletin/syllabus URLs registered via Day-3 source lifecycle (**STAGED**). Independent PDF review/activation for production official replica remains **NOT_VERIFIED**; synthetic harness activation is labelled and test-only.
- Synthetic demonstrations: `backend/app/jee_main_exam_intelligence/fixtures.py`, tests under `backend/tests/test_day11_*.py`, `python -m app.day11_verify --json`.

## Task acceptance matrix

| ID | Approved task | Evidence / implementation path | Status |
|---|---|---|---|
| D11-01 | Freeze Day11 scope/provenance matrix | `docs/execution/D11-SCOPE-MAP.md` (this file) | PARTIAL |
| D11-02 | Register 2027 official information bulletin | `source_authority.register_nta_2027_candidate_sources` | PARTIAL |
| D11-03 | Register 2027 syllabus source | same | PARTIAL |
| D11-04 | Official extraction/review workflow | `source_authority.evaluate_official_pattern_authority` + `TrustExecutionMode`; synthetic JSON cannot satisfy `PRODUCTION` (`test_day11_trust.py`) | PARTIAL |
| D11-05 | Reuse canonical `ExamPack` and `ExamVersion` | `exam_catalogue.ensure_jee_main_exam_catalogue` | PASS |
| D11-06 | Section hierarchy in existing `ExamSection` | `exam_catalogue._ensure_paper1_sections_and_rules` | PASS |
| D11-07 | Official blueprint/scoring `ExamBlueprintRule` | typed rules in `exam_catalogue` (`verified_official: false` until NTA approval) | PARTIAL |
| D11-08 | Amendments and pattern drift | `source_authority.detect_source_drift` | PARTIAL |
| D11-09 | Referential, tenant and author checks | `question_pool._trusts_item`, `trusted_validation`, production Day6 bind (`verify_production_day6_binding`) | PARTIAL |
| D11-10 | Subject selector and canonical catalogue | `enums.JeeMainSubjectCode`, `syllabus_mapping.validate_subject_code` | PASS |
| D11-11 | Versioned official chapter/topic mapping | `syllabus_mapping.OFFICIAL_JEE_MAIN_2027_TOPICS` (catalogue seed, not full NTA ingest) | PARTIAL |
| D11-12 | Link existing curriculum nodes | `curriculum_linkage.OFFICIAL_TOPIC_CURRICULUM_REFS` (catalogue refs only; no invented edges) | PARTIAL |
| D11-13 | Syllabus/version guard | `syllabus_mapping.syllabus_guard_passes` | PARTIAL |
| D11-14 | Past-paper/answer-key source inventory | `historical_evidence.SYNTHETIC_HISTORICAL_INVENTORY` (metadata only) | PARTIAL |
| D11-15 | Shift-level historical tagging | `HistoricalPaperProvenance` model | PARTIAL |
| D11-16 | Explainable historical frequency analytics | `historical_evidence.build_historical_analytics_report` | PARTIAL |
| D11-17 | Soft statistical priors versus official requirements | `is_mandatory_nta_quota: false` in priors | PASS |
| D11-18 | Typed `PaperPlanRequest/Result` | `contracts.py` | PASS |
| D11-19 | Single-subject exact-count practice | `planner._plan_practice`, `test_day11_planner.py::test_practice_mathematics_exactly_ten` | PASS |
| D11-20 | Topic-filtered exact-count practice | derived `algebra` group, `test_practice_algebra_exactly_ten_no_filler` | PASS |
| D11-21 | Full Paper-1 replica mode | `SYNTHETIC_FIXTURE` 75 PASS; `PRODUCTION` FAIL until NTA PDF (`test_day11_trust.py`) | PARTIAL |
| D11-22 | Section/type quotas | `allocator.allocate_full_replica_slots` (60 MCQ / 15 numerical) | PASS |
| D11-23 | Versioned marks and response rules | `blueprint_snapshot.load_verified_blueprint_for_version`, scoring canonical slot types | PARTIAL |
| D11-24 | Bounded quota allocator | `allocator.py` | PASS |
| D11-25 | Difficulty/cognitive/competency distribution | `paper_distribution_bridge.evaluate_plan_paper_distribution` + `test_day11_r2.py` | PARTIAL |
| D11-26 | Infeasible-constraint verdict | issue codes + adversarial tests | PARTIAL |
| D11-27 | Reuse Day-8 LangGraph + AnythingLLM gateway | `live_generation.apply_live_generation_boundary` + idempotent `claim_idempotency`; slot-fill graph NOT COMPLETE | PARTIAL |
| D11-28 | Question/answer validity | `question_pool._answer_valid` | PARTIAL |
| D11-29 | Repair and count invariants | count mismatch fail-closed; bounded repair not wired | PARTIAL |
| D11-30 | Evidence and provenance in each item | question `metadata_json`, plan checksum | PARTIAL |
| D11-31 | Scoring simulation metadata | `scoring.build_scoring_preview` 60 MCQ / 15 numerical (`test_synthetic_replica_passes_with_explicit_fixture_mode`) | PASS |
| D11-32 | Persist `TestDefinition` / `TestQuestion` safely | tenant scope, slot marks in checksum, replay/idempotency tests (`test_day11_r2.py`) | PARTIAL |
| D11-33 | Deterministic reference fixtures | `fixtures.py`, `question_pool.seed_synthetic_question_pool` | PASS |
| D11-34 | Adversarial matrix | `test_day11_*.py`, `day11_verify._adversarial_matrix` (foreign tenant under `PRODUCTION`) | PASS |
| D11-35 | `day11_verify`, migrations and targeted CI | `verdict: synthetic_fixture_pass`, exit 0 on pass; `.github/workflows/targeted-ci.yml` step; Alembic `20261109_0018` | PASS |
| D11-36 | Chief Architect review + Founder signoff gate | **PENDING** Founder “Cursor completed” + manual review | PENDING |

## Fixed acceptance gates

| Gate | Required proof | Current state |
|---|---|---|
| NTA 2027 bulletin/syllabus | Verified original PDFs, page locators, checksums, source approval, versioned exam blueprint | **NOT_VERIFIED** (URLs staged; synthetic JSON harness only in CI) |
| Practice 10 Mathematics | 10 valid Mathematics questions | **PASS** (synthetic fixture harness) |
| Practice 10 Algebra | 10 valid mapped Algebra questions | **PASS** (synthetic fixture harness) |
| Full Paper-1 replica | Approved source-defined structure | **PARTIAL** (75/60+15 synthetic after harness activation only) |
| Syllabus/answer trust | Fail closed on bad authority | **PARTIAL** (production Day6 bind + synthetic mode separation; no live NTA PDF) |
| Replay/checkpoint | Idempotent `TestDefinition` by plan checksum | **PARTIAL** (tenant scope + conflict code; worker restart tests limited) |
| Compatibility | SQLite, Ruff, Mypy on Day11 modules | **PASS** (focused) |
| D11-36 | Final SHA, full regression, Founder signoff | **PENDING** |

**Governance:** `founder_approval` remains `false`; Day12 locked; Day4 Issue #12 evidence gate unchanged; live PostgreSQL / Founder UAT not run.
