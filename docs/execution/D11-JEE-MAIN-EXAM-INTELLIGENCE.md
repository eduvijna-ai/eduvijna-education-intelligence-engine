# Day 11 — JEE Main Examination Intelligence: **FOUNDER-APPROVED IMPLEMENTATION SPECIFICATION**

**Status: FOUNDER APPROVED — IMPLEMENTATION AUTHORIZED (2026-11-10).** Approval signal: “Approved to start cursor handoff.” Authorized scope: D11-01…D11-36. Day-11 implementation branch is `feature/day11-jee-main-exam-intelligence` and must use a Draft PR against `develop`.
**Prerequisite:** Day 10 PR #29 merged to `develop` at `1c25312c78a39858fa4899c3fe5afac5b31a2328`; Day 10 Founder engineering signoff recorded. Founder has now given that separate authorization. Work only in the dedicated Day-11 feature branch; Day-12 and later implementation remain locked. No Founder Day-11 completion signoff or merge approval has been issued.

**Project objective:** Source-backed, versioned JEE Main Paper 1 (B.E./B.Tech.) ExamPack and generic paper planner, supporting **exact requested counts** for subject/topic practice and **true full-pattern replicas**. No JEE Advanced/CUET/CLAT (Days 12–13), no learner mastery/test runner (later day), no REST/MCP/UI (later day), no unlicensed copying of past papers.

## Current source and pattern gate (as of 2026-11-10)
- **Authority:** [NTA JEE Main documents](https://jeemain.nta.nic.in/documents/) lists **Information Bulletin 2027** and **Syllabus 2027**; candidate 2027 bulletin PDF: https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/10/202610241890224107.pdf ; syllabus PDF: https://cdnbbsr.s3waas.gov.in/s3f8e59f4b2fe7c5705bf878bbd494ccdf/uploads/2026/10/20261024683680768.pdf .
- **Candidate 2027 Paper 1 structure** (secondary transcriptions consistent with 2026 baseline, **must be verified directly against downloaded/approved NTA 2027 PDF before activating as official**): Mathematics, Physics, Chemistry; each 20 Section-A MCQs + 5 Section-B integer numerical responses; **75 questions / 300 marks**, +4 right / -1 wrong / 0 unattempted for both, 3-hour paper. Never use an article/analysis to activate official requirements.
- **Authority hierarchy:** original NTA bulletin/syllabus and published amendments = **hard constraints**; authentic previous papers/keys = historical evidence; coaching/aggregator weightage = **nonbinding statistical estimates**; teacher preference/user counts = practice requests, never an unlabelled official replica.
- If NTA fetch blocks, use existing Source Intelligence approved **manual official PDF upload / metadata / checksum / review** route; mark source missing and **fail closed on official replica**, rather than copying secondary summaries into official policy.

## Phase A — authoritative ExamPack and versioning

| ID | Task | Concrete acceptance |
|---|---|---|
| **D11-01** | Freeze Day11 scope/provenance matrix | `D11-SCOPE-MAP` maps D11-01…36 to code, tests, citations; no Day12+ scope. |
| **D11-02** | Register 2027 official information bulletin | Stage exact NTA PDF URL, publication/source revision, checksum, retrieved time, authority and approval status; missing/disputed source = NOT VERIFIED. |
| **D11-03** | Register 2027 syllabus source | Stage versioned official Mathematics, Physics and Chemistry syllabus; provenance and extracted section locators. |
| **D11-04** | Official extraction/review workflow | Stage → extract/diff → validate source text → curator approves → activate; tampered/expired/unsigned source never gains authority. |
| **D11-05** | Reuse canonical `ExamPack` and `ExamVersion` | One JEE Main pack, distinct 2026/2027 versions and effective dates; do not overwrite historical pattern. |
| **D11-06** | Section hierarchy in existing `ExamSection` | Paper 1 → Mathematics/Physics/Chemistry → Section A/B with ordered IDs and source locators; no 2A/2B implementation. |
| **D11-07** | Official blueprint/scoring `ExamBlueprintRule` | Represent verified per-section counts, question types, total marks, negative marking and numerical rounding as versioned typed data, not hardcoded planner constants. |
| **D11-08** | Amendments and pattern drift | New NTA bulletin/notice creates candidate revision; diff/approval needed before replacement, no silent active-policy mutation. |
| **D11-09** | Referential, tenant and author checks | Linked `SourceRevision`, exam/section/rule version IDs, no cross-version attachment; audit who approved and when. |

## Phase B — syllabus alignment and historical intelligence

| ID | Task | Concrete acceptance |
|---|---|---|
| **D11-10** | Subject selector and canonical catalogue | Recognize official Mathematics, Physics, Chemistry subject codes; reject unknown alias/subject. |
| **D11-11** | Versioned official chapter/topic mapping | Import only NTA-listed 2027 concepts with exact source, subsection and checksum; unknown/inferred topic explicitly distinguished. |
| **D11-12** | Link existing curriculum nodes | Match approved concept/LO/prerequisite graph from Days 2/4/6/10 without inventing official NTA or CBSE relationships. |
| **D11-13** | Syllabus/version guard | Out-of-syllabus, stale grade/version, wrong subject or unverified topic blocks official mode. |
| **D11-14** | Past-paper/answer-key source inventory | Version year/session/date/shift, subject, question number, official provenance, rights; no copyrighted PDF or question bank committed. |
| **D11-15** | Shift-level historical tagging | Track question type, topic, marks, answer status, source/evidence quality; no inferred exact official topic distribution. |
| **D11-16** | Explainable historical frequency analytics | Reproducible counts + denominators + years/shifts sampled, smoothing/uncertainty, low-sample warnings and audit/source references. |
| **D11-17** | Soft statistical priors versus official requirements | Historical chapter weights are optional hints; explicit user/topic choice and official section quotas take precedence, never fabricated NTA chapter quotas. |

## Phase C — generic paper planner and exact-count guarantees

| ID | Task | Concrete acceptance |
|---|---|---|
| **D11-18** | Typed `PaperPlanRequest/Result` | Exam version, mode, subject(s), chapter/topic, requested count, difficulties, quota constraints, source refs, plan checksum. |
| **D11-19** | Single-subject **exact-count** practice | `JEE Main → Mathematics → 10` yields **exactly 10 validated items**, not the 25-item full subject replica. |
| **D11-20** | Topic-filtered exact-count practice | `Mathematics → Algebra → 10` yields exactly 10 approved Algebra-tagged items; reject off-topic filler and unjustified auto-broadening. |
| **D11-21** | Full Paper-1 replica mode | Once NTA 2027 bulletin is approved, generate **75 total** with exactly 25 per each of 3 subjects; mark as 2027 official-pattern replica, not the original NTA paper. |
| **D11-22** | Section/type quotas | Each subject exactly **20 MCQ + 5 numerical** in full-replica mode, with no optional Section B if verified 2027 source confirms this. |
| **D11-23** | Versioned marks and response rules | Correctly attach +4/-1/0, allowed integer-entry and numeric-answer/rounding instructions, 3-hour metadata, distinct section IDs. |
| **D11-24** | Bounded quota allocator | Deterministic allocation, rounding/ties, split subject counts, no duplicate IDs or unplanned surplus; practice targets do not masquerade as full exam replica. |
| **D11-25** | Difficulty/cognitive/competency distribution | Apply existing Day-6 taxonomy and Day-10 paper evaluator, with correct count vs mark weights and source-backed optional difficulty estimates. |
| **D11-26** | Infeasible-constraint verdict | No authorized content, impossible topic quota, conflicting ranges, insufficient valid items, or unapproved official policy → typed FAIL/REVIEW, never silent count changes. |

## Phase D — generation and auditable result assembly

| ID | Task | Concrete acceptance |
|---|---|---|
| **D11-27** | Reuse Day-8 LangGraph + AnythingLLM gateway | One bounded generation path, no new orchestrator/provider SDK, no direct LLM vendor calls. |
| **D11-28** | Question/answer validity | MCQ options/one correct answer, numerical exact/rounded response + explanation, equations/units/LaTeX validation and source alignment; no unverifiable answer PASS. |
| **D11-29** | Repair and count invariants | Retry/replace only failed items within existing bounded repair; final requested count exact or honest non-PASS, deterministic deduplication. |
| **D11-30** | Evidence and provenance in each item | Bind exam/syllabus version, topic ID, official-vs-derived flag, source checksum, model/gateway audit and validator output. |
| **D11-31** | Scoring simulation metadata | Compute score preview/maximum/negative marks for prepared paper; do not implement later learner attempt/session UI. |
| **D11-32** | Persist `TestDefinition` / `TestQuestion` safely | Stable paper/run/version/checksum, idempotent reruns, no duplicate audit/LLM calls or cross-tenant leakage, no cross-section question reuse. |

## Phase E — Founder acceptance and CI

| ID | Task | Concrete acceptance |
|---|---|---|
| **D11-33** | Deterministic reference fixtures | Approved *synthetic* 10-question Math, Algebra-filtered 10, full 75 with 60 MCQ/15 numerical and expected marks/sections. |
| **D11-34** | Adversarial matrix | Forged bulletin, stale syllabus, official-source drift, fake historical weights, NTA/CBSE scope confusion, bad answers, duplicates, 9/11 for requested 10, 74/76 for full 75, foreign tenant. |
| **D11-35** | `day11_verify`, migrations and targeted CI | Ruff/Mypy, Day11 + impacted Day2/3/6/7/8/9/10, SQLite migration and PG DDL compilation, exact SHA, no CI green by skipping tests. |
| **D11-36** | Chief Architect review + Founder signoff gate | Frozen HEAD, one full historical regression, independent manual review and explicit Founder approval; PR Draft until approved; Founder all-days localhost/Docker UAT still deferred, not passed. |

### Founder acceptance demonstrations (internal, not React UI)
1. **Practice:** Mathematics `requested_count=10` → 10; Mathematics/Algebra `requested_count=10` → 10 Algebra-only.
2. **Replica:** JEE Main 2027 Paper 1 → 75 validated questions, 25 each Mathematics/Physics/Chemistry, each 20 MCQ+5 numerical, +4/-1/0, max 300, version/source displayed **after direct official bulletin verification**.
3. **Security/rejection:** unverified official bulletin or changed policy → replica NOT PASS; out-of-syllabus/foreign tenant/incorrect answer and impossible quotas → bounded typed failure; no invented NTA topic quotas.
4. **Replay:** restarting after partial generation produces same intended final paper and no unauthorized duplicate audits or model calls.

### Strict governance
- Day11 issue/tasklist **APPROVED FOR IMPLEMENTATION** on 2026-11-10. Cursor implementation is authorized only for D11-01…D11-36 on a Draft PR; do not mark `founder_approval: true`, merge, activate Day12, or claim production acceptance without later separate Founder signoff.
- Day4 NCF/NCERT source completeness follow-up and D5-DS01/#16 remain separate release-evidence items; do not fake official curriculum authority.
- Source ordering: NTA official > original official paper/answer key > clearly sourced historical analytics > teacher preference. Persist revision-specific hard rules only after authorized source review.
- This approval does not authorize production deployment, full UAT, JEE Advanced, CUET, CLAT or learner tracking.


## Chief Architect delivery protocol (approved scope; implementation only)

- **Builder:** Cursor, standard Composer 2.5 (not Fast); no paid overage/parallel builders. GitHub is the source of truth.
- **Review:** Founder notifies ChatGPT "Cursor completed"; Chief AI Architect reviews exact GitHub HEAD and CI independently. Keep PR Draft until separate Founder signoff.
- **Milestones:** A source authority (D11-01–09), B syllabus/history (10–17), C planner/quotas (18–26), D validated content/persistence (27–32), E acceptance (33–36). Preserve traceability across phases; don't request seven separate review rounds for adjacent bugs.
- **Sources:** The 2027 NTA URLs in this document are discovery candidates. Capture and approve original bulletin/syllabus before activating hard rules; if unavailable, ship explicit NOT VERIFIED and fail-closed official replica, while synthetic fixture-based tests may still run.
- **Test strategy:** Ruff/mypy, Day11 focused + impacted Day2/3/6/7/8/9/10 per change, exact SHA verifiers and migration parity; one full historical regression at D11-36 after manual code-review clean. Do not treat a skip as pass.
- **Acceptance:** exactly 10 valid Math, exactly 10 approved Algebra-mapped, official 75/300 replica only when source-approved, rejection on 9/11 or 74/76, replay idempotency and no unauthorized model calls.
- **Existing exceptions:** Day4 official-source evidence temporarily deferred under Issue #12; D5-DS01 #16 OPEN; Founder localhost/Docker UAT deferred to final all-days UAT, NOT PASSED; live PostgreSQL NOT RUN until separately evidenced.
