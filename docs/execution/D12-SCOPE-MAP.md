# Day 12 — JEE Advanced 36-task scope and evidence matrix

**Status:** Founder-approved for implementation 2026-11-12. No Day12 business tasks implemented at branch bootstrap. All 36 initially **NOT_STARTED**. D12-36 separately requires Chief Architect review and explicit Founder completion signoff.
**Authoritative specification:** [Issue #33](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/33). The task list, phases, and exact acceptance criteria are approved and must not be silently reduced.
**Branch:** `feature/day12-jee-advanced-intelligence`, originating from `develop@1f7bff808cbddd979a9161823d42458a5d68eb88`. **Do not import the unfinished Day11 PR #31.**
**Day11 dependency exception:** Day11 has **13 PASS / 22 PARTIAL ON_HOLD / 1 D11-36 PENDING**. Founder explicitly approved Day12 implementation while Day11 unfinished acceptance remains held for final all-days review. Neither Day11 signoff nor merge/waiver follows.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D12-01 | Freeze scope and dependency exception | `backend/app/jee_advanced/governance.py` | PARTIAL | Governance record + tests; per-task evidence matrix still in progress |
| D12-02 | Register JEE Advanced 2026 official brochure/syllabus | `backend/app/jee_advanced/source_registry.py` | SOURCE_PENDING | Discovery URLs staged; no curator-approved SHA/revision |
| D12-03 | Register 2026 Paper 1, Paper 2 and final answer keys | — | NOT_STARTED | — |
| D12-04 | Curator validation and amendment lifecycle | — | NOT_STARTED | — |
| D12-05 | 2026 reference vs 2027 candidate authority | `backend/app/jee_advanced/authority.py` | PARTIAL | Fail-closed 2027 + unapproved 2026 reference; tests in `test_day12_m0_governance.py` |
| D12-06 | Reuse ExamPack/ExamVersion | `backend/app/jee_advanced/exam_profile.py` | PARTIAL | Pack bootstrap; test `test_day12_exam_profile.py` |
| D12-07 | Two-paper ExamSection hierarchy | `backend/app/jee_advanced/exam_profile.py` | PARTIAL | Paper1/Paper2 + PCM; blueprint counts unpinned until sources |
| D12-08 | Paper-specific versioned ExamBlueprintRule | — | NOT_STARTED | — |
| D12-09 | Subject and syllabus catalogue | — | NOT_STARTED | — |
| D12-10 | Existing curriculum/LO linkage | — | NOT_STARTED | — |
| D12-11 | Strict scope/version guard | — | NOT_STARTED | — |
| D12-12 | Advanced reasoning-demand profile | — | NOT_STARTED | — |
| D12-13 | Historical official-paper inventory | — | NOT_STARTED | — |
| D12-14 | Question type/marking evidence tagging | — | NOT_STARTED | — |
| D12-15 | Explainable historical analytics | — | NOT_STARTED | — |
| D12-16 | Official constraint vs soft-prior precedence | — | NOT_STARTED | — |
| D12-17 | Typed AdvancedPaperPlanRequest/Result | `backend/app/jee_advanced/contracts.py` | PARTIAL | Core contracts; planner integration partial |
| D12-18 | Exact-count subject practice | `backend/app/jee_advanced/practice_service.py` | PARTIAL | Synthetic Math×10; `test_day12_practice.py` |
| D12-19 | Topic-filtered practice | `backend/app/jee_advanced/practice_service.py` | PARTIAL | Synthetic Algebra×10; Eduvijna-derived topic group |
| D12-20 | Paper 1 standalone planner | `backend/app/jee_advanced/planner.py` | NOT_STARTED | Authority shell only |
| D12-21 | Paper 2 standalone planner | `backend/app/jee_advanced/planner.py` | NOT_STARTED | Authority shell only |
| D12-22 | Two-paper combined simulation | `backend/app/jee_advanced/planner.py` | PARTIAL | Pair guard + synthetic checksums; `test_day12_adversarial.py` |
| D12-23 | Evidence-backed answer families | — | NOT_STARTED | — |
| D12-24 | Paper-/item-specific scoring rules | `backend/app/jee_advanced/scoring.py` | PARTIAL | MCQ/multi/numerical vectors; paper-specific pinning pending |
| D12-25 | Deterministic constrained allocator | — | NOT_STARTED | — |
| D12-26 | Paper cognitive/competency review | — | NOT_STARTED | — |
| D12-27 | Reuse Day8 AnythingLLM/LangGraph | — | NOT_STARTED | — |
| D12-28 | Independent MCQ and multiselect answer verifier | — | NOT_STARTED | — |
| D12-29 | Independent numerical/expression verifier | — | NOT_STARTED | — |
| D12-30 | STEM assets and formulas | — | NOT_STARTED | — |
| D12-31 | Bounded repair, dedup and traceability | — | NOT_STARTED | — |
| D12-32 | Persist and replay two-paper TestDefinition | — | NOT_STARTED | — |
| D12-33 | Synthetic reference fixtures | `backend/app/jee_advanced/synthetic_fixtures.py` | PARTIAL | Labelled pool; not two-paper full demo yet |
| D12-34 | Adversarial acceptance suite | — | NOT_STARTED | — |
| D12-35 | Day12 verifier and regression gates | `backend/app/day12_verify.py` | PARTIAL | Initial `--json` gates; full CI scope pending |
| D12-36 | Independent review and Founder signoff | — | NOT_STARTED | — |

## Acceptance rules
- Update each task with exact implementation paths, deterministic test IDs and original source checksum/page/curator evidence if source-dependent; use `PARTIAL`, `SOURCE_PENDING` or `NOT_STARTED` honestly.
- The **2026** JEE Advanced official papers are reference only until approved from original IIT/JAB sources; **2027 official replica must fail closed** until independently approved originals exist.
- Practice request 10 Math / 10 Algebra must return exactly 10 independently validated questions or a typed non-PASS, never filler.
- Full reference simulation requires both source-approved Paper1 and Paper2; independently reproduce paper-specific type/marking rules, including multi-select partial credit and numerical policy.
- Do not fabricate official per-paper question counts, total marks, JEE Advanced 2027 syllabus/rules, historical frequencies, source checksums, or human curator decisions.
- No bulk copyrighted papers, live secrets or learner PII in Git.
- Run impacted tests during work, exact-head targeted CI and migration checks, one final frozen-head `pytest tests/`; Draft Compose SKIP is not PASS.
- D12-36 remains PENDING until independent exact-SHA Architect review and separate Founder approval. Day13 stays locked; Founder all-days UAT remains deferred and unpassed.