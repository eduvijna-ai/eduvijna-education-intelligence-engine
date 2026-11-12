# D11 closure evidence ledger (D11-CLOSE-01)

**Baseline HEAD (start):** `c962d4cafd7577b160f94b18883f7928a3d912f5`  
**Matrix:** 13 PASS / 22 PARTIAL / 1 PENDING (D11-36)  
**Updated:** 2026-11-11 — Milestone 0–1 in progress

## Legend

| Verdict | Meaning |
|---------|---------|
| PASS | Engineering + evidence complete per frozen D11 spec |
| PARTIAL | Executable engineering or guard present; acceptance gap remains |
| SOURCE_PENDING | Curator-approved original source not yet bound |
| PENDING | D11-36 final gate only |

## Milestone 1 — production correctness (engineering)

| ID | Evidence | Tests | Verdict | Blocker |
|----|----------|-------|---------|---------|
| D11-27 | `live_generation.complete_live_generation_plan` pool-first before gateway; `gateway_resolve.resolve_live_generation_gateway` only on shortage | `test_live_generation_boundary_*`, `test_day11_pgc02_*` | PARTIAL | Live AnythingLLM not run |
| D11-28 | `_production_independent_trust_ok` binds canonical hash + solver item_id; orchestration-only trust envelope | `test_production_persist_*` in PGC-01/02 | PARTIAL | General JEE solver; numerical fail-closed |
| D11-29/32 | File checkpoint close/reopen HITL | `test_durable_hitl_reopens_*` | PARTIAL | Subprocess worker restart NOT RUN |
| D11-09/30 | Day6 + orchestration trust required for APPROVED | PGC-02 persist tests | PARTIAL | Day9 veto on generated boundary not fully evidenced |

## Milestone 2 — NTA 2027 source (SOURCE_PENDING until curator)

| Item | Status |
|------|--------|
| Official portal | `https://jeemain.nta.nic.in/documents/` lists Bulletin/Syllabus 2027 |
| Candidate PDF URLs | HTTP 200 / `application/pdf` on bulletin candidate URL (2026-11-11 probe); **SHA/curator activation NOT VERIFIED** |
| Curator activation | **NOT_VERIFIED** — no `official_pattern_verified` in production |
| Manual path | See `D11-NTA-SOURCE-BLOCKER.md` |

**Tasks D11-02,03,04,07,08,11,21,23:** SOURCE_PENDING until SHA/locator/approver exists.

## Milestone 3 — historical papers

| Item | Status |
|------|--------|
| 2027 historical exams | **N/A** (future vs 2026-11-11) |
| Prior-year metadata | PARTIAL — synthetic inventory only until lawful ingest |
| D11-14,15,16 | SOURCE_PENDING / PARTIAL |

## Milestone 5 — regression

| Check | Status |
|-------|--------|
| Targeted `.eduvijna/pytest-targets.txt` | Run each closure push |
| Full `pytest tests/` | **NOT RUN** until engineering+source gates ready |
| `day11_verify` | `synthetic_fixture_pass`; `official_2027_nta_approved: false` |
| D11-36 | **PENDING** Founder signoff |

## Governance

- No merge, `founder_approval: false`, Day12 locked until D11-36.
- Founder authorization permits **work** on source tasks, not self-approval of NTA PDFs.


## Chief Architect direct implementation (2026-11-12)

**This is engineering/source-discovery progress, NOT D11-36 acceptance.** The
Founder requested direct completion because Cursor is unavailable.

| Area | Direct implementation | Evidence / limitation |
|---|---|---|
| Day8 production answer provenance (D11-09/28/30) | The Day11 trust envelope is now checked against a **completed persisted `OrchestrationIdempotencyRecord` and saved `OrchestrationResult`**, including the exact saved draft and solver/Day6 entries. Request-provided labels alone cannot impersonate a completed run. | `orchestration_bridge._production_trust_envelope_allowed`, targeted PGC02 tests; no claim that a generic JEE numerical solver is complete |
| Test-harness separation | Deterministic trust-envelope bypass requires a **session-controlled test-only capability**, not merely a known metadata token in the request. | `_TEST_ENVELOPE_SESSION_FLAG`, PGC02 negative test |
| Cross-tenant idempotency (D11-32) | An existing global `Question.external_code` must match tenant, exam version, question text, type, answer and options or it is rejected as a replay conflict. | `_existing_generated_question_matches`, collision regression |
| Official blueprint integrity (D11-07/21/23) | Verified production snapshot now rejects any missing/duplicate subject-section rule, incomplete marking, absent pinned sources, inconsistent total, or unequal counts that the allocator cannot represent. It never substitutes candidate defaults. | `blueprint_snapshot.load_production_blueprint_snapshot`, synthetic test-only rule consistency regressions; real NTA approval still absent |
| 2026 historical discovery (D11-14) | Nine NTA-linked April 2026 Paper-1 shift URLs are recorded without copying question text. | `historical_evidence.OFFICIAL_2026_PAPER_DISCOVERY`; status **LINK_DISCOVERED, not ORIGINAL_VERIFIED**; no hashes, rights clearance or topic counts |

### Required non-delegable NTA curator evidence

The official portal at https://jeemain.nta.nic.in/documents/ lists
**Information Bulletin 2027** and **Syllabus 2027**, but the two candidate
2027 PDF download URLs were not retrievable through the assistant's available
PDF channels on 2026-11-12. **No original PDF bytes, SHA-256 checksum,
publication/version text, page locators, or human curator signatures have
been independently verified.** Do not set `approved_by`,
`official_pattern_verified` or `verified_official` from this ledger.

For each original document, an authorized person must obtain it from the
official portal, run the existing `SourceIntelligenceService` PDF ingest,
extraction, source diff and validation, review the actual extracted version and
section locators, then perform *explicit* approve-and-activate actions with
audited identity. Source checksum, source-diff, approval fingerprint and
original storage bytes must be consistent. After that, pin the exact active
revisions to the 2027 `ExamVersion` and review each versioned section rule.

The nine 2026 paper links above require separate rights and original-file
review before item-level tagging or statistical sampling. No 2027 examination
shifts exist in November 2026, and historical topic weights must remain
nonbinding until real paper-level evidence supports the counts.

**Do not change task PASS counts or unlock production/Day12 on this basis.**
A frozen-head full historical regression, live infrastructure/UAT evidence
when available, full source-attested positive replica, independent final
review and explicit Founder D11-36 approval remain required.
