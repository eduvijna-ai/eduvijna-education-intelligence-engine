# Day 15 — Learner Intelligence scope and evidence matrix

**Status:** **0 PASS / 35 PARTIAL / 0 SOURCE_PENDING / 1 NOT_STARTED = 36 rows** (D15-MECHANICAL-CONTAINMENT-SEAL-01; runtime persistence **DISABLED**; D15-36 pending).  
**Authoritative specification:** [Issue #56](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/56).  
**Branch:** `feature/day15-learner-intelligence`. Day11 ON_HOLD; Day14 containment; Day15 ACTIVE `founder_approval:false`; Day16 LOCKED.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D15-01 | Scope and dependency freeze | `governance.py`, `test_day15_m0_governance.py` | PARTIAL | Matrix + deferrals frozen; D15-36 not signed |
| D15-02 | Canonical learner identity | `context.py`, tenancy `Learner` | PARTIAL | Server-resolved tenant; synthetic IDs in tests only |
| D15-03 | Learner profile persistence | `models/learner_intelligence.py`, `LearnerProfileVersion` | PARTIAL | Versioned profile; unknown explicit |
| D15-04 | Data model and migration | `20261124_0022_day15_learner_intelligence.py` | PARTIAL | Additive; PG 0021 blocker unchanged |
| D15-05 | Assessment eligibility gate | `harness.py`, `eligibility.py`, `test_day15_adversarial.py` | PARTIAL | Catalog attestation only; production unconditionally blocked |
| D15-06 | Attempt lifecycle | `lifecycle.py`, `test_day15_mechanical_seal.py` | PARTIAL | Sealed stubs; no runtime transitions |
| D15-07 | Issued assessment snapshot | `snapshot.py`, fingerprint binding | PARTIAL | Server fingerprint; no learner key leak |
| D15-08 | Answer capture | `lifecycle.py` | PARTIAL | Contained: no runtime DB capture |
| D15-09 | Draft save and resume | `lifecycle.py` | PARTIAL | Contained: resume persistence disabled |
| D15-10 | Objective scoring | `scoring.py`, `test_day15_scoring.py` | PARTIAL | Decimal exact; no client trust |
| D15-11 | Multi/numeric scoring | `scoring.py` | PARTIAL | Unsupported → REVIEW_REQUIRED |
| D15-12 | Descriptive/rubric boundary | `scoring.py` | PARTIAL | Pending review excluded from mastery |
| D15-13 | Test score aggregation | `scoring.py`, `finalization.py` | PARTIAL | Section/subject/total from snapshots |
| D15-14 | Atomic final submission | `finalization.py` | PARTIAL | Contained: finalize blocked at runtime |
| D15-15 | Idempotency and replay | `finalization.py` | PARTIAL | Deferred: no durable replay in containment |
| D15-16 | Question history | `history.py` | PARTIAL | Distinct observations; no replay dupes |
| D15-17 | Concept attribution | `mastery.py` | PARTIAL | Day6 mapping only; unknown excluded |
| D15-18 | Mastery model v1 | `D15-MASTERY-POLICY-v1.md`, `mastery.py` | PARTIAL | Deterministic v1; no IRT claim |
| D15-19 | Concept mastery updates | `mastery.py` | PARTIAL | Eligible events only; audit trail |
| D15-20 | Topic/curriculum rollups | `rollups.py` | PARTIAL | Denominators; no double count |
| D15-21 | Cognitive performance | `rollups.py` | PARTIAL | Day6 tags; unclassified bucket |
| D15-22 | Difficulty performance | `rollups.py` | PARTIAL | Small-sample guard |
| D15-23 | Exam performance | `rollups.py` | PARTIAL | Mode/version isolation |
| D15-24 | Selected-option diagnosis | `diagnostics.py` | PARTIAL | Day9 tags on wrong answers |
| D15-25 | Correction patterns | `diagnostics.py` | PARTIAL | Formula/calc/concept patterns |
| D15-26 | Prerequisite gap evidence | `diagnostics.py` | PARTIAL | Day10 hypothesis not conclusion |
| D15-27 | Diagnostic profile aggregation | `diagnostics.py` | PARTIAL | Frequencies + source attempt IDs |
| D15-28 | Learner memory/preferences | `memory.py` | PARTIAL | Provenance; no PII in repo |
| D15-29 | History and recomputation | `memory.py`, `service.py` | PARTIAL | Restart replay parity |
| D15-30 | Read/query contracts | `query.py` | PARTIAL | Internal tenant-scoped; redaction |
| D15-31 | Day16 handoff contract | `handoff.py` | PARTIAL | Typed gaps only; no scheduling |
| D15-32 | Privacy and lifecycle | `privacy.py` | PARTIAL | Least privilege boundaries |
| D15-33 | Adversarial and DB compatibility | `test_day15_adversarial.py` | PARTIAL | SQLite file-backed; live PG NOT_RUN |
| D15-34 | Founder verifier | `day15_verify.py`, `test_day15_verify_sha.py` | PARTIAL | Containment + pure diagnostic verifier |
| D15-35 | CI and acceptance evidence | targeted CI, ruff, mypy | PARTIAL | Compose SKIPPED if draft |
| D15-36 | Independent acceptance and stop | — | NOT_STARTED | Awaiting Founder + Architect |

## Governance anchors

- Day14 **academic validation/issuance DISABLED** — learner production eligibility uses **synthetic harness only**.
- Day11 #31 ON_HOLD; Day12/13/14 deferral ledgers preserved.
- **postgresql_migration_0021:** BLOCKER_DEFERRED_NOT_PASSED (no edit to 0021).
- No REST/MCP/UI (Days 17–18), no adaptive generation (Day 16).