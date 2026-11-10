# Day 11 — scope, implementation and evidence map

**Status: FOUNDER-APPROVED FOR IMPLEMENTATION, ENGINEERING PENDING.** Founder authorization on **2026-11-10**: “Approved to start cursor handoff.” This map is a **baseline skeleton**, not proof that any Day11 feature is implemented.

- Canonical specification: `docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md` and [Issue #30](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/30).
- Baseline: `develop` at `1f7bff808cbddd979a9161823d42458a5d68eb88`. Branch: `feature/day11-jee-main-exam-intelligence`; PR to remain Draft until final Founder signoff.
- Hard authority gate: original NTA **2027** bulletin and syllabus `SourceRevision` review/approval required before any purported **official-pattern** replica. All draft values remain `NOT_VERIFIED` until sourced.
- Count invariant: custom practice 10 = **exactly 10 validated**; full replica = officially verified subject/section quotas. Never silently reduce count or fill with off-topic/unvalidated questions.
- Legacy reuse: `ExamPack`, `ExamVersion`, `ExamSection`, `ExamBlueprintRule`, `TestDefinition`, `TestQuestion`, source lifecycle, Day6/9/10 validators, Day8 checkpoint and AnythingLLM gateway.
- Future-day exclusions: no JEE Advanced, CUET, CLAT, learner mastery, REST/MCP/UI, full Founder localhost UAT or production release.
- Preserved backlog: Day4 official evidence [Issue #12](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/12) temporarily deferred by Founder; D5-DS01 Issue #16 stays open.
- Review: Founder “Cursor completed” -> Chief AI Architect exact GitHub HEAD code/CI review; no self-approval/merge/Day12 unlock.

## Task acceptance matrix — update *actual* code/test paths and status as work lands

| ID | Approved task | Evidence / implementation path | Status |
|---|---|---|---|
| D11-01 | Freeze Day11 scope/provenance matrix | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-02 | Register 2027 official information bulletin | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-03 | Register 2027 syllabus source | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-04 | Official extraction/review workflow | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-05 | Reuse canonical `ExamPack` and `ExamVersion` | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-06 | Section hierarchy in existing `ExamSection` | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-07 | Official blueprint/scoring `ExamBlueprintRule` | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-08 | Amendments and pattern drift | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-09 | Referential, tenant and author checks | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-10 | Subject selector and canonical catalogue | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-11 | Versioned official chapter/topic mapping | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-12 | Link existing curriculum nodes | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-13 | Syllabus/version guard | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-14 | Past-paper/answer-key source inventory | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-15 | Shift-level historical tagging | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-16 | Explainable historical frequency analytics | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-17 | Soft statistical priors versus official requirements | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-18 | Typed `PaperPlanRequest/Result` | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-19 | Single-subject **exact-count** practice | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-20 | Topic-filtered exact-count practice | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-21 | Full Paper-1 replica mode | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-22 | Section/type quotas | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-23 | Versioned marks and response rules | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-24 | Bounded quota allocator | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-25 | Difficulty/cognitive/competency distribution | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-26 | Infeasible-constraint verdict | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-27 | Reuse Day-8 LangGraph + AnythingLLM gateway | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-28 | Question/answer validity | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-29 | Repair and count invariants | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-30 | Evidence and provenance in each item | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-31 | Scoring simulation metadata | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-32 | Persist `TestDefinition` / `TestQuestion` safely | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-33 | Deterministic reference fixtures | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-34 | Adversarial matrix | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-35 | `day11_verify`, migrations and targeted CI | PENDING — identify exact source, code function and focused test when implemented | PENDING |
| D11-36 | Chief Architect review + Founder signoff gate | PENDING — identify exact source, code function and focused test when implemented | PENDING |

## Fixed acceptance gates (do not mark PASS until evidenced)

| Gate | Required proof | Current state |
|---|---|---|
| NTA 2027 bulletin/syllabus | Verified original PDFs, page locators, checksums, source approval, versioned exam blueprint | NOT_VERIFIED |
| Practice 10 Mathematics | 10 **valid** and authorized Mathematics questions, no surplus or missing | PENDING |
| Practice 10 Algebra | 10 valid mapped Algebra questions, zero off-topic filler | PENDING |
| Full Paper-1 replica | Approved source-defined structure, count/type/marks/scoring, 75 only if officially confirmed | PENDING |
| Syllabus/answer trust | Outside-source, wrong-answer, forged or stale rules fail closed | PENDING |
| Replay/checkpoint | Exact-count stable paper/audit IDs with no duplicated successful gateway calls | PENDING |
| Compatibility | SQLite/Alembic and PostgreSQL DDL, Ruff/Mypy, impacted historical tests | PENDING |
| D11-36 | Final candidate SHA, one full historical regression, independent code review, Founder signoff | PENDING |

**UAT and deployment:** Founder localhost/Docker UAT is deferred to all-days acceptance and never presumed passed; live PostgreSQL is not evidenced. D11 completion/merge require a later explicit Founder authorization.
