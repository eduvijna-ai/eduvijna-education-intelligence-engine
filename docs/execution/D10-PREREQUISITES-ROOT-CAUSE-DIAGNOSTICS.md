# Day 10 — Prerequisites & Root-Cause Diagnostics, plus Paper-Level Cognitive / Competency Distribution

**STATUS: FOUNDER APPROVED — IMPLEMENTATION AUTHORIZED (2026-10-27).**
**Prerequisite:** Day 9 Founder signed off on 2026-10-19, PR #27 merged to `develop`. Docker/localhost UAT expressly deferred by Founder until all development days; it remains mandatory before production and is NOT marked PASS.
**Founder authorization (2026-10-27):** “Approved and authorized implementation.” D10-01…D10-36 implementation through Cursor is permitted in a separate Draft feature PR against `develop`; independent Chief AI Architect exact-HEAD review and explicit Founder Day-10 signoff remain mandatory before merge or Day 11. No production deployment, provider bypass, Codex or all-days UAT now.

## Objective and canonical input boundaries

Build a **generic, versioned, evidence-bound prerequisite concept graph**, and use approved Day-9 misconception/diagnostic signals to produce **auditable possible prerequisite/root-cause hypotheses** — NOT claims of demonstrated individual learner mastery. In the same Day-10 milestone, evaluate **paper-level cognitive and competency distribution** for already-supplied valid items using Day-6 taxonomies; do not generate or plan exam-specific papers.

Reuse existing:
- **Day 2:** `ConceptPrerequisite` model, `CurriculumNode`, `CurriculumVersion`, `LearningOutcome`, `Competency`.
- **Days 3–5:** authoritative SourceRevision lifecycle, NCF/NCERT/CBSE/Telangana versioned curriculum, LO and concept mapping. D5-DS01 issue #16 stays OPEN; no fabricated Telangana content.
- **Day 6:** `ValidationRun`, cognitive evidence/levels and competency authority; existing provenance/policy/quality guard. Locked v1 cognitive levels are **Remember, Understand, Apply, Analyze, Evaluate** (NOT Create); competency categories are **Knowledge, Conceptual Understanding, Application, Analysis, Problem Solving, HOTS**.
- **Day 7:** approved scoped evidence/citations and tenancy.
- **Day 8:** single LangGraph execution, gateway, audit, bounded repair, checkpoint/idempotency/HITL.
- **Day 9:** approved misconception taxonomy, wrong-option evidence-linked tags and validation verdicts.

**Not in Day 10:** official JEE/CLAT/CUET etc paper blueprints, section/marks/negative marking and actual exam quota engines (Days 11–14); individual learner attempt ingestion/mastery/profiling (Day 15); remediation/adaptive learning plans (Day 16); REST/MCP/jobs (Day 17); React UI (Day 18); Founder localhost UAT now (scheduled for final all-days UAT).

## Phase A — prerequisite graph foundations (D10-01…D10-10)

| ID | Task | Required acceptance |
|---|---|---|
| **D10-01** | Freeze Day-10 scope map | Map 36 tasks to exact code/test/evidence; guard Days 11+ and Day-6/7/8/9 boundaries. |
| **D10-02** | Reuse Day-2 `ConceptPrerequisite` persistence | Adopt existing directed concept-edge schema; no parallel graph DB/new dependency. Propose migrations only if unavoidable, with SQLite and PostgreSQL compatibility plan. |
| **D10-03** | Versioned graph contracts | Typed `PrerequisiteGraphScope`, node/edge/path and snapshot contracts; stable IDs, curriculum/academic version, grade, medium, subject, relation type, strength, provenance and status. |
| **D10-04** | Source-backed edge provenance | Each purported official prerequisite relationship must reference an approved exact source revision/locator. Synthetic and inferred edges explicitly labelled and never misrepresented as official. |
| **D10-05** | Edge integrity validator | Reject unknown/non-concept nodes, duplicate/self-links, invalid weight, inactive references and unjustified cross-subject/version links; no silent model-created edges. |
| **D10-06** | Cycle and progression validation | Detect cycles/multi-hop loops, contradictory ordering and unsupported grade progression; bounded deterministic failure/review. |
| **D10-07** | Curriculum and tenant scope isolation | Verify edges/nodes against exact curriculum version, grade/year, medium, subject and authorized org/institution/teacher scope; prevent transitive cross-tenant leakage. |
| **D10-08** | Versioned graph assembly / lifecycle | Deterministically assemble approved graph snapshots from existing canonical edges; stable checksums, active/superseded lifecycle, audit and idempotent refresh. No raw RAG scraping to invent edges. |
| **D10-09** | Bounded graph traversal | Reusable ancestors/descendants/shortest explanatory paths with `max_depth`, `max_nodes`, `max_paths`, deterministic tie-breaking; prevent runaway traversal/N+1. |
| **D10-10** | Graph quality, contradiction and audit report | Report disconnected concepts, missing provenance, cycles, unknown nodes, stale versions and conflicting evidence as structured issue codes with review-required outcomes. |

## Phase B — explainable prerequisite/root-cause hypotheses (D10-11…D10-22)

| ID | Task | Required acceptance |
|---|---|---|
| **D10-11** | Diagnostic request contract | Accept canonical question/option context, validated Day-9 tag(s), misconception taxonomy version, concept/LO/competency scope and source-bound graph snapshot. No personal learner record required. |
| **D10-12** | Misconception → concept mapping | Versioned mapping from approved misconception codes to implicated concepts/error mechanisms, with explicit source/synthetic lineage; unknown mappings fail/review. |
| **D10-13** | Eligibility and authority preflight | Only validated diagnostic wrong-option signals may infer possible root cause; a correct option, Day-6-blocked question or rejected Day-9 tag cannot yield a PASS root-cause assertion. |
| **D10-14** | Candidate prerequisite resolver | Resolve graph candidates within exact curriculum/subject/grade/LO/competency scope; no invented nodes or model-free-form identifiers. |
| **D10-15** | Bounded backward root-cause traversal | Trace plausible prerequisite paths from the observed misconception to earlier concepts, with depth/size limits and exact ordered evidence paths. |
| **D10-16** | Deterministic hypothesis ranking | Rank paths by explicitly versioned support criteria such as specificity, graph distance, edge strength/authority and signal quality — **not an uncalibrated learner-probability claim**. |
| **D10-17** | Alternative and competing hypotheses | Return multiple plausible prerequisite paths with supporting/refuting evidence; avoid asserting one certain psychological cause without proof. |
| **D10-18** | Contradiction and uncertainty policy | No path, weak evidence, circular dependencies, unknown mapping or conflicting authoritative material → structured `REVIEW_REQUIRED` / `INSUFFICIENT_EVIDENCE`; no fabricated certainty. |
| **D10-19** | Curriculum, LO and competency consistency | Align root-cause paths with target LO, concept progression and Day-6 competency/cognitive rules; do not convert LO tagging into a new curriculum authority. |
| **D10-20** | Day-7 provenance / tenant security | Each explanation evidence ref must resolve to authorized visible source revisions in the current context; treat source text as untrusted, reject foreign/unbound/forged refs. |
| **D10-21** | Structured root-cause result/verdict/audit | Result has item/option ID, misconception code, candidate concepts, ordered paths, support/uncertainty, issue codes, versions, exact citation/revision refs, review instructions and audit refs; no CoT/secrets/raw source text. |
| **D10-22** | Day-8/9 integration and HITL | Add internal optional root-cause stage via existing Day-8 LangGraph/checkpoint/audit/idempotency/HITL; do not build a second orchestrator/gateway or create learner mastery state. Unaffected passing items stay unchanged. |

## Phase C — paper-level cognitive & competency distribution (D10-23…D10-30)

| ID | Task | Required acceptance |
|---|---|---|
| **D10-23** | Generic paper-distribution request/result | Evaluate an already-supplied canonical set of question IDs/marks/Day-6 validated cognitive/competency metadata. Enforce exact requested count/cardinality and stable item identity. **No paper generation or exam-specific planner.** |
| **D10-24** | Cognitive-level actual distribution | Counts and percentages across exactly **Remember, Understand, Apply, Analyze, Evaluate**; reject silent aliases or unapproved `Create` as a v1 level. |
| **D10-25** | Competency actual distribution | Counts and percentages across **Knowledge, Conceptual Understanding, Application, Analysis, Problem Solving, HOTS**; use versioned Day-6 taxonomy/validated tags. |
| **D10-26** | Multi-label attribution policy | Explicitly choose primary-label or split-weight attribution for multiply tagged items; prevent double counting and report per-category denominator/coverage. |
| **D10-27** | Count-based vs mark-weighted distribution | Return both where requested, validate marks (including zero/missing/invalid), duplicate IDs, dropped/blocked items and exact denominators; no silently inflated totals. |
| **D10-28** | Versioned generic distribution target policy | Support user/institution/board-authorized **generic** exact/range percentages and required levels with source/version/override precedence. Do NOT implement official JEE, CLAT or CUET section blueprints, exam marks rules or topic quotas. |
| **D10-29** | Deterministic integer target reconciliation | Handle percentages summing to 100, ranges, fractional quotas, largest-remainder/tie-breaking and impossible count/marks constraints; infeasible rules → explicit issue/review rather than silently changing item count. |
| **D10-30** | Distribution evaluator and audit verdict | Compare observed vs requested targets; structured status, deviation, uncovered/invalid metadata, field paths, and audit refs. A paper may FAIL a distribution target even when each question individually PASSES Day-6. No auto-generate/replace questions. |

## Phase D — acceptance, boundary and CI (D10-31…D10-36)

| ID | Task | Required acceptance |
|---|---|---|
| **D10-31** | Deterministic positive fixtures | Build source-labelled synthetic 3–5 concept prerequisite DAG, Day-9 misconception mapping/root-cause paths, and a 10-question synthetic paper matching a known cognitive/competency mix. No live RAG/AI required. |
| **D10-32** | Adversarial and negative fixtures | Cycles, wrong academic version/grade/subject, foreign tenant, fake citations, inactive/unknown concepts, contradictory edges, correct option tagged as error, Day-6 veto, ambiguous/no root cause, invalid quotas, duplicate paper items, over-100% targets, count-vs-marks mismatch, injection-like evidence. |
| **D10-33** | Batch, replay, SQLite/PostgreSQL compatibility | Multi-item diagnosis and paper evaluation deterministic; no duplicate audit/model calls on restart; migration only if genuinely required. Prove SQLite/Alembic upgrade/check and static PG DDL; label live PG untested if unavailable. |
| **D10-34** | Founder verifier `app.day10_verify` | JSON and readable mode, exact `EDUVIJNA_CANDIDATE_SHA`, graph/tenant/cycle/root-cause/uncertainty/distribution demonstration, audit and no Day11+ scope violations. |
| **D10-35** | Targeted CI and test/evidence map | Ruff, Mypy, new D10 tests and impacted D2/6/7/8/9 boundary tests; `.eduvijna/pytest-targets.txt` changes minimal; no expensive full regression in repair loops; Compose if runtime/dependency changes demand it. |
| **D10-36** | Final engineering/Founder acceptance | All D10-01…D10-35 traceable and passing; Chief Architect manual exact-HEAD review CLEAN; one controlled full historical regression at frozen acceptance SHA; SQLite/PG compatibility; Founder signoff/merge only by explicit instruction. As Founder decided, **localhost UAT deferred until all development days**, not passed or waived; no automatic Day-11 unlock or production approval. |

## Founder demonstration requirements

**Demo A — prerequisite / possible root cause:**
A synthetic mathematics concept chain, e.g., `counting sequence → whole-number addition → multi-step addition`, with an approved Day-9 **OFF_BY_ONE_LOW** tag at the target concept. Show two bounded alternative prerequisite hypotheses, exact path, evidence refs, support rank and `REVIEW_REQUIRED` for missing/uncertain evidence. This is **not** a claim that a real learner has a weakness.

**Demo B — cognitive distribution:**
Ten validated synthetic questions with cognitive labels `2 Remember, 2 Understand, 4 Apply, 1 Analyze, 1 Evaluate` → counts `2/2/4/1/1`, percentages `20/20/40/10/10`. A deliberately mismatched target must give a structured **paper-level** non-PASS while its individually valid questions remain unchanged. Competency distribution also shown with six locked categories and explicit multi-label handling. All targets in this demo are **synthetic examples, not official CBSE/JEE allocations**.

**Demo C — rejection/security:**
Reject wrong-tenant graph edge/citation; fail/review for cycle, unknown prerequisite, correct option as "misconception", stale version, missing root-cause path, or impossible distribution quota. A Day-6 blocked item must never be reinstated by the root-cause engine. Verify replay/human review and zero unapproved model calls.

## Governance and Founder decision

- **Founder approved D10-01…D10-36 on 2026-10-27 and explicitly authorized implementation.**
- Implement on dedicated Day-10 feature branch using a Draft PR and scoped `@cursor` handoff, with exact-HEAD manual ChatGPT reviews and targeted incremental tests.
- **`implementation_authorized: true`**, but **`founder_approval: false`** until the later explicit D10-36 signoff; no automatic merge or Day-11 activation.
- D5-DS01/#16 remains open; Day-9 deferred Docker/localhost UAT is carried to the final Founder UAT before production.


---

## Implementation execution protocol — Chief AI Architect (no change to approved scope)

**GitHub approval source:** Issue #28, Founder message of 2026-10-27: "Approved and authorized implementation."
**Baseline:** `develop` at `4fccb05aa890d8aabb87e8394fb23231677ff1de`, Day-9 merge `4fccb05…`.
**Branch:** `feature/day10-prerequisites-root-cause-diagnostics`; Draft PR to `develop`, issue #28; do not start Day11.
**Review loop:** Founder → Cursor standard Composer 2.5 (not Fast) → targeted local verification → push exact-HEAD CI → Founder message "Cursor completed" → Chief AI Architect independent manual exact-HEAD review → focused repairs until clean. Codex is **not** part of the default loop. Never self-merge.

### Important implementation boundaries
- Implement the graph on the **existing** SQLAlchemy `ConceptPrerequisite` edges (two concept-node FKs, `relation_type`, bounded `weight`, `metadata_json`); inspect Day-2 lifecycle constraints. No separate graph database, no invented official source provenance or inferred official edges.
- Prefer a framework-independent `app/prerequisite_intelligence/` and a distribution evaluation module. Reuse Day-6 registry version `cognitive-competency-v1.0`; do **not** add a cognitive level `create` or silently treat it as `evaluate`.
- When hypotheses lack source, edge proof or sufficient Day-9 signal, use structured `REVIEW_REQUIRED` or `INSUFFICIENT_EVIDENCE`. Do not infer a named learner's actual ability, mastery or remediation.
- Day-10 paper distribution **evaluates** supplied validated items. It does not create questions, plan JEE/CUET/CLAT section counts, or replace items to meet targets. Any synthetic 10-item cognitive mix is a **demonstration**, not official exam distribution.
- Reuse Day-7 approved scoped `SourceRevision` and Day-8 existing `GenerationGateway` if an optional model call is justified. Avoid adding any model call if deterministic graph mapping/ranking suffices. No direct provider SDK or new retrieval HTTP.
- `.eduvijna/execution-state.yml`: Day10 ACTIVE with tasklist APPROVED, but `founder_approval:false` until separate completion signoff; Day11 LOCKED. D5-DS01/#16 stays OPEN.
- Incremental Ruff/Mypy plus **only Day10 and affected Day2/6/7/8/9 tests** during implementation/repair. Run `day8_verify` and `day9_verify` on every exact HEAD and add `app.day10_verify`. No expensive full historical regression until D10-36 final acceptance after Chief Architect manual code review CLEAN.
- Localhost/Docker UAT is **deferred by Founder to all-days UAT** and **not passed/waived**; continue creating deterministic unit/integration evidence and clean focused CI during implementation. PostgreSQL production must remain portable (SQLite local).
- D10-01…D10-36 acceptance evidence must be updated in `docs/execution/D10-SCOPE-MAP.md` per task; no task can be marked CLEAN just because a mocked test returned success. Preserve issue #28 as the approved authoritative list.

### Completion handback for implementation phase
Publish exact 40-char PR HEAD, changed files per task, focused Ruff/Mypy/pytest counts, `day8_verify`/`day9_verify`/`day10_verify` results, tenant/edge cycle/root-cause/negative-case evidence, migration statement, boundary safeguard, and targeted GitHub CI run IDs/status. Then **STOP** for Founder "Cursor completed" → independent Chief AI Architect review. No merge, Founder signoff, production or Day11 until explicitly authorized.
