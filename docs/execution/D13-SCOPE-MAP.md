# Day 13 — CUET UG / CLAT UG 36-task scope and evidence matrix

**Status:** **0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED = 36 rows** (engineering checkpoint; D13-36 not Founder-accepted).  
**Authoritative specification:** [Issue #52](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/52).  
**Branch:** `feature/day13-cuet-clat-intelligence`. Day11 ON_HOLD; Day13 ACTIVE `founder_approval:false`; Day14 LOCKED.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D13-01 | Freeze scope and dependency exception | `governance.py`, `test_day13_m0_governance.py` | PARTIAL | Matrix initialized; D13-36 not signed |
| D13-02 | Primary-source manifest | `source_registry.py`, `constants.PRIMARY_SOURCE_MANIFEST` | PARTIAL | URLs only; no staged bytes |
| D13-03 | CUET 2026 official authority | `source_registry.cuet_reference_evidence_ready` | SOURCE_PENDING | No curator SHA |
| D13-04 | CUET syllabi and mediums | `scope_guard.validate_cuet_medium`, `exam_profile.py` | PARTIAL | No ACTIVE syllabus revision |
| D13-05 | CLAT 2027 primary authority | `authority.resolve_clat_authority` | SOURCE_PENDING | Consortium bytes not staged |
| D13-06 | Rights and future CUET versions | `authority.resolve_cuet_authority`, trust guards | PARTIAL | 2027 CUET fail-closed only |
| D13-07 | CUET ExamPack + ExamVersion | `exam_profile.ensure_cuet_clat_exam_packs` | PARTIAL | Synthetic bootstrap only |
| D13-08 | Registered test catalogue | `constants.CUET_TEST_CATALOGUE_SIZE` | PARTIAL | Count constant; not DB catalogue |
| D13-09 | Single-test paper rules | `practice_service.assemble_single_test`, `constants` | PARTIAL | Synthetic 50; official SOURCE_PENDING |
| D13-10 | Language/medium integrity | `scope_guard.validate_cuet_medium` | PARTIAL | Typed non-PASS for bad medium |
| D13-11 | Syllabus/concept mapping | — | PARTIAL | Fail-closed placeholder; no ACTIVE mapping |
| D13-12 | Exact-count practice | `practice_service.allocate_practice`, `test_day13_f03a_persisted.py`, `test_day13_f03a_iter3.py` | PARTIAL | F03-A iter3: institution scope, tenant-first selection, active Day6 proof |
| D13-13 | Per-test full-paper 50 | `practice_service.assemble_single_test` | PARTIAL | Synthetic 50; official NOT_READY |
| D13-14 | Future-year CUET isolation | `authority.resolve_cuet_authority` 2027 | PARTIAL | Fail-closed tested |
| D13-15 | CLAT ExamPack/version | `exam_profile.py`, `constants.CLAT_PACK_CODE` | PARTIAL | Isolated pack |
| D13-16 | Duration/marking 120/+1/-0.25 | `constants`, `scoring.py` | PARTIAL | Unit-level scoring |
| D13-17 | Five section range constraints | `constants.CLAT_SECTION_RANGES` | PARTIAL | Encoded approximate ranges |
| D13-18 | Feasible range allocator | `section_allocator.py` | PARTIAL | Deterministic sum==120 |
| D13-19 | Passage→question clusters | `passage_clusters.py`, `clat_planner.py` | PARTIAL | Original demo passages |
| D13-20 | English comprehension | `copyright_passages.py` | PARTIAL | Demo passage only |
| D13-21 | Legal reasoning | `copyright_passages.py` | PARTIAL | Demo passage only |
| D13-22 | Logical reasoning | `copyright_passages.py` | PARTIAL | Demo passage only |
| D13-23 | Current Affairs + GK RAG | `clat_current_affairs_evidence.py`, `test_day13_f04a_*.py` | PARTIAL | F04-A iter3: fail-closed tenant/receipt/forgery/pack scope, binding@v3 |
| D13-24 | Quantitative techniques | `copyright_passages.py` | PARTIAL | Demo table passage |
| D13-25 | Copyright-safe passages | `copyright_passages.ORIGINAL_PASSAGE_LIBRARY` | PARTIAL | Short original texts only |
| D13-26 | Source/time answer binding | — | PARTIAL | Fingerprints on fixtures |
| D13-27 | Reuse Day6/9/10 validators | — | PARTIAL | Not wired in this slice |
| D13-28 | Day7/8 orchestration | — | PARTIAL | No direct provider calls |
| D13-29 | Score family validation | `scoring.py`, `test_day13_scoring.py` | PARTIAL | CUET/CLAT mark rules |
| D13-30 | Tenant isolation | `scope_guard.validate_tenant` | PARTIAL | Guard present |
| D13-31 | Durable persistence/replay | `replay_store.py`, `test_day13_replay.py` | PARTIAL | In-process only |
| D13-32 | Whole-paper verification | `clat_planner`, `day13_verify.py` | PARTIAL | Synthetic 120 + clusters |
| D13-33 | Synthetic adversarial fixtures | `test_day13_adversarial.py` | PARTIAL | Count/range/replay vectors |
| D13-34 | Scoped integration regression | `test_day13_core.py` | PARTIAL | Day13 tests only |
| D13-35 | `day13_verify` and CI | `day13_verify.py`, `test_day13_verify_sha.py` | PARTIAL | Targeted CI hook |
| D13-36 | Independent review + Founder signoff | — | NOT_STARTED | Awaiting Founder |

## Acceptance rules

- Synthetic demonstration must never be claimed as curator-approved CUET 2026 or CLAT 2027 official replica.
- `cuet_reference_curator_approved` and `clat_official_curator_approved` remain false until real evidence exists.
- Full historical `pytest tests/` — final acceptance checkpoint only.