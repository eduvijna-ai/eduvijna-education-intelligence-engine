# Day 12 — JEE Advanced 36-task scope and evidence matrix

**Status:** D12-CORE-01 candidate handback (Issue #35). **0 PASS / 21 PARTIAL / 2 SOURCE_PENDING / 13 NOT_STARTED.** D12-36 PENDING Chief Architect + Founder signoff.
**Authoritative specification:** [Issue #33](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/33).
**Branch:** `feature/day12-jee-advanced-intelligence` (PR #34). Day11 ON_HOLD; Day12 ACTIVE `founder_approval:false`; Day13 LOCKED.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D12-01 | Freeze scope and dependency exception | `jee_advanced/governance.py`, `test_day12_m0_governance.py` | PARTIAL | Governance record; matrix updated candidate 3 |
| D12-02 | Register brochure/syllabus | `source_registry.py`, `source_lifecycle.py`, `test_day12_assembly.py` | SOURCE_PENDING | Six slots staged via Day3 register; no curator-approved SHA |
| D12-03 | Register Paper1/Paper2 and keys | `source_registry.py` (slots 3–6), `source_lifecycle.py` | SOURCE_PENDING | Metadata registered; no original PDF bytes ingested |
| D12-04 | Curator validation lifecycle | `source_authority.py`, `source_lifecycle.py`, `test_day12_core.py` | PARTIAL | DB-backed authority chain; production curator still SOURCE_PENDING |
| D12-05 | 2026 reference vs 2027 authority | `authority.py`, `test_day12_m0_governance.py` | PARTIAL | Fail-closed 2027; reference blocked without curator |
| D12-06 | Reuse ExamPack/ExamVersion | `exam_profile.py`, `test_day12_exam_profile.py` | PARTIAL | Pack bootstrap; no reference blueprint pinned |
| D12-07 | Two-paper ExamSection hierarchy | `exam_profile.py`, `test_day12_exam_profile.py` | PARTIAL | Paper1/Paper2 + PCM; counts unpinned |
| D12-08 | Paper-specific ExamBlueprintRule | — | NOT_STARTED | Requires approved paper instructions |
| D12-09 | Subject and syllabus catalogue | — | NOT_STARTED | Official syllabus ingest pending |
| D12-10 | Curriculum/LO linkage | — | NOT_STARTED | — |
| D12-11 | Strict scope/version guard | `scope_guard.py`, `trust_guard.py`, `test_day12_practice.py` | PARTIAL | Trust/profile guards; no full tenant matrix |
| D12-12 | Advanced reasoning-demand profile | — | NOT_STARTED | — |
| D12-13 | Historical official-paper inventory | — | NOT_STARTED | Rights/originals not in repo |
| D12-14 | Question type/marking evidence tagging | `synthetic_fixtures.py` metadata | PARTIAL | Demo types only; not source-backed items |
| D12-15 | Explainable historical analytics | `historical_analytics.py`, `test_day12_assembly.py` | PARTIAL | NOT_ANALYZABLE default; no item-level stats |
| D12-16 | Official constraint vs soft-prior | — | NOT_STARTED | — |
| D12-17 | Typed AdvancedPaperPlanRequest/Result | `contracts.py`, planner tests | PARTIAL | Contracts + planner; no reference replica |
| D12-18 | Exact-count subject practice | `practice_service.py`, `persisted_practice.py`, `test_day12_core.py` | PARTIAL | Synthetic default; persisted Math×10 path with labeled test fixtures |
| D12-19 | Topic-filtered practice | `practice_service.py`, `persisted_practice.py`, `test_day12_core.py` | PARTIAL | Synthetic default; persisted Algebra×10 with Day6 metadata gate |
| D12-20 | Paper 1 standalone planner | `planner.py`, `test_day12_adversarial.py` | PARTIAL | Synthetic PCM assembly; not official replica |
| D12-21 | Paper 2 standalone planner | `planner.py`, `test_day12_adversarial.py` | PARTIAL | Same; demonstration_only |
| D12-22 | Two-paper combined simulation | `planner.py`, `synthetic_paper_assembly.py`, adversarial/assembly tests | PARTIAL | 6×PCM demo items/paper; not full official paper |
| D12-23 | Evidence-backed answer families | `scoring.py`, `source_attested_scoring.py` | PARTIAL | Session-attested preview; official IIT/JAB rubrics SOURCE_PENDING |
| D12-24 | Paper/item-specific scoring rules | `scoring.py`, `source_attested_scoring.py`, `test_day12_core.py` | PARTIAL | Rule validation + attested preview with test-seeded revisions |
| D12-25 | Deterministic constrained allocator | `synthetic_paper_assembly.py`, `test_day12_assembly.py` | PARTIAL | Quota validation; not full blueprint allocator |
| D12-26 | Paper cognitive/competency review | — | NOT_STARTED | Day10 integration not wired |
| D12-27 | Reuse Day8 LangGraph/AnythingLLM | — | NOT_STARTED | — |
| D12-28 | Independent MCQ/multiselect verifier | — | NOT_STARTED | — |
| D12-29 | Independent numerical verifier | — | NOT_STARTED | — |
| D12-30 | STEM assets and formulas | — | NOT_STARTED | — |
| D12-31 | Bounded repair and dedup | — | NOT_STARTED | — |
| D12-32 | Persist/replay two-paper TestDefinition | `paper_pair_persistence.py`, `test_day12_core.py` | PARTIAL | SQLite idempotent replay + cross-process test; PG live NOT_RUN |
| D12-33 | Synthetic reference fixtures | `synthetic_fixtures.py`, assembly/adversarial tests | PARTIAL | PCM two-paper demo; explicit demonstration_only |
| D12-34 | Adversarial acceptance suite | `test_day12_*.py` (8 files incl. `test_day12_core.py`) | PARTIAL | CORE adversarial paths; full matrix NOT_RUN |
| D12-35 | Day12 verifier and CI gates | `day12_verify.py`, targeted-ci, `test_day12_verify_sha.py` | PARTIAL | sha_alignment required; DB authority; reference flags false |
| D12-36 | Independent review and Founder signoff | — | NOT_STARTED | Awaiting Chief Architect exact-HEAD review |

## Acceptance rules
- Synthetic demonstration must never be claimed as curator-approved 2026 reference or 2027 official replica.
- `reference_2026_curator_approved` and `official_2027_approved` remain false until real evidence exists.
- Full historical `pytest tests/` — **NOT RUN** on candidate 3 (per implementation iteration policy).
- D12-36 remains PENDING until separate Founder signoff.
