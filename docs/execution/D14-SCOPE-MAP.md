# Day 14 — CA Foundation, IMAT, TG EAPCET scope and evidence matrix

**Status:** **0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED = 36 rows** (`D14-SAFETY-CONTAINMENT-01`; academic validation/issuance disabled; D14-36 not Founder-accepted).  
**Authoritative specification:** [Issue #54](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/54).  
**Branch:** `feature/day14-ca-imat-eapcet-intelligence`. Day11 ON_HOLD; Day14 ACTIVE `founder_approval:false`; Day15 LOCKED.

| ID | Approved task | Evidence / test IDs | State | Blocker / remaining proof |
|---|---|---|---|---|
| D14-01 | Scope and dependency freeze | `governance.py`, `test_day14_m0_governance.py` | PARTIAL | Matrix initialized; D14-36 not signed |
| D14-02 | Primary authority manifest | `constants.PRIMARY_SOURCE_MANIFEST`, `source_registry.py` | PARTIAL | URLs/locators only; no staged bytes |
| D14-03 | Source approval gates | `source_registry.*_evidence_ready` | SOURCE_PENDING | No curator SHA for ICAI/MUR/TGCHE |
| D14-04 | Version and authority isolation | `authority.py` | PARTIAL | Fail-closed gates tested synthetically |
| D14-05 | Generic ExamPack configuration | `exam_profile.py` | PARTIAL | Synthetic bootstrap via ExamPack model |
| D14-06 | CA Foundation scheme pack | `constants.CA_PAPER_CODES`, `ca_planner.py` | PARTIAL | Four-paper synthetic bundle demo |
| D14-07 | CA Accounting mapping | `ca_descriptive.py`, synthetic stems | PARTIAL | Original demo multipart; no ACTIVE syllabus DB |
| D14-08 | CA Business Laws mapping | `ca_descriptive.py` | PARTIAL | Versioned session fail-closed; demo only |
| D14-09 | CA Quantitative Aptitude mapping | `practice_service.py`, `synthetic_fixtures.py` | PARTIAL | Independent arithmetic in synthetic pool |
| D14-10 | CA Business Economics mapping | `synthetic_fixtures.py` | PARTIAL | Objective synthetic pool |
| D14-11 | CA descriptive item contract | `contracts.DescriptiveItemContract` | PARTIAL | Rubric multipart; no auto grading claim |
| D14-12 | CA rubric validation | `scoring.validate_rubric_marks` | PARTIAL | Marks-sum check; limited adversarial |
| D14-13 | CA objective scoring | `scoring.score_ca_objective` | PARTIAL | Descriptive/objective separation tested |
| D14-14 | CA exact-count and paper planner | `ca_planner.py`, `test_day14_core.py` | PARTIAL | Synthetic exact-count; official SOURCE_PENDING |
| D14-15 | CA session evidence and tests | `authority.resolve_ca_authority` | PARTIAL | Future session drift fail-closed |
| D14-16 | IMAT annual decree profile | `imat_planner.py`, `constants` | PARTIAL | Reference counts; decree bytes SOURCE_PENDING |
| D14-17 | IMAT syllabus mappings | `synthetic_fixtures.build_imat_pool` sections | PARTIAL | Section labels; no annex-attested mapping DB |
| D14-18 | IMAT question and independent solver | `imat_solver_check.py` | PARTIAL | Synthetic pass; no live solver persistence |
| D14-19 | IMAT exact-count/full paper | `imat_planner.py` | PARTIAL | 60-Q synthetic full paper |
| D14-20 | IMAT scoring and source drift | `scoring.score_imat_decimal` | PARTIAL | Decimal totals; future-year veto |
| D14-21 | TG EAPCET versioned streams | `eapcet_planner.py`, `EapcetStream` | PARTIAL | Two stream profiles synthetic |
| D14-22 | EAPCET Engineering mapping | `constants.EAPCET_ENGINEERING_SECTIONS` | SOURCE_PENDING | 80/40/40 only after official attestation |
| D14-23 | EAPCET Agriculture & Pharmacy mapping | `constants.EAPCET_AP_SECTIONS_REFERENCE` | PARTIAL | Reference distribution synthetic |
| D14-24 | EAPCET bilingual integrity | `eapcet_bilingual.py` | PARTIAL | Typed unsupported medium failure |
| D14-25 | EAPCET exact-count/full paper | `eapcet_planner.py` | PARTIAL | 160-Q synthetic; official NOT_READY |
| D14-26 | Extensibility proof | `extensibility_proof.py`, `test_day14_extensibility.py` | PARTIAL | Static scan; no forbidden generic branches |
| D14-27 | Historical evidence and copyright | `historical_evidence.py` | PARTIAL | Model only; no bulk ICAI ingestion |
| D14-28 | Shared educational validators | `validation_bridge.py` | PARTIAL | Day6/9/10 not wired in this slice |
| D14-29 | Shared orchestration and knowledge | `validation_bridge.py` | PARTIAL | No direct LLM; Day7/8 reuse deferred |
| D14-30 | Canonical issuance and persistence | `persistence_bridge.attempt_canonical_issuance`, `test_day14_persistence.py` | PARTIAL | DB issuance for validated synthetic only; no production claim |
| D14-31 | Whole-paper quality and scoring | `paper_quality.py` | PARTIAL | Duplicate/section checks synthetic |
| D14-32 | Adversarial regression | `test_day14_adversarial.py` | PARTIAL | Cross-year/tenant/forgery vectors partial |
| D14-33 | Database compatibility | `exam_profile.py` (SQLite in tests) | PARTIAL | PG 0021 blocker unchanged; no new migration |
| D14-34 | Founder verifier | `day14_verify.py`, `test_day14_verify_sha.py` | PARTIAL | Synthetic mode CI hook |
| D14-35 | Exact-head CI and evidence | targeted CI, ruff, mypy, scoped pytest | PARTIAL | Compose/PG/AnythingLLM NOT_RUN |
| D14-36 | Independent acceptance and stop | — | NOT_STARTED | Awaiting Founder |

## Safety containment (D14-SAFETY-CONTAINMENT-01)

| R3 finding | Containment status | Remaining closure |
|---|---|---|
| R3-01 persistence | **DISABLED** — `attempt_canonical_issuance` is NOT_READY only; no DB I/O | Trusted tenant-bound canonical issuance (D14-30) |
| R3-02 source trust | **DISABLED** — all curator flags hard false | Day3 curator authority chain |
| R3-03 academic validation | **DISABLED** — no PASS delivery; solver not proof | Independent solver + unique content (D14-09/18/25/31) |
| R3-04 scope/planners | Gates active; synthetic planners report structural targets only | Strict scope matrix + marks truth (D14-04..14) |
| R3-05 bilingual | REVIEW_REQUIRED without persisted equivalence evidence | Curator-attested translation evidence |
| R3-06 extensibility/bridges | NOT_READY; `pack_config_driven=False` | Config-driven onboarding + Day6–10/7/8 integration |

Baseline candidate SHA for containment: `4a755cc5d89b06146aa7b32f9d169c6c6f805d71`.

## Acceptance rules

- Synthetic demonstration must never be claimed as curator-approved ICAI, MUR IMAT, or TGCHE official replica.
- `ca_icai_curator_approved`, `imat_decree_curator_approved`, and `eapcet_official_curator_approved` remain false until real evidence exists.
- EAPCET Aglasem mirror is discovery-only and must not activate official mode.
- Full historical `pytest tests/` — final acceptance checkpoint only.