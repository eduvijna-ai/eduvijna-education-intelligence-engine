# Day 6 — Education Intelligence Validators

Base: `a40c28a3167d9cee0b6ec0e4944ed414fc2a4dd6` on `develop`. Founder signed off Day 5 on 2026-10-07. Day 5 merge commit is `5d3927b5e582b2c5aa898b5e755bfbb194eca74b`. D5-DS01 remains deferred and open as issue #16; Day 6 must not weaken or bypass that source gate.

## Objective

Build Eduvijna's deterministic, auditable Education Intelligence validation layer on top of the merged canonical domain/source/curriculum architecture.

By the Day 6 completion gate, Eduvijna must be able to accept a canonical assessment-item or assessment-set fixture and return versioned validation results for:
- locked cognitive/Bloom levels;
- competency tagging;
- learning-outcome alignment;
- rubric integrity;
- design-time difficulty;
- age/grade appropriateness;
- cognitive progression primitives (per-item; paper-level distribution is Day 10);
- educational quality;
- bias/safety;
- country/board/institution policy constraints.

Day 6 validates supplied content and metadata. It does **not** generate questions, call AnythingLLM, orchestrate LangGraph, implement exam planners, generate diagnostic distractors, or perform learner remediation.

## Locked taxonomy boundary

Seed the ARIV/frozen v1 competency taxonomy:
- knowledge
- conceptual_understanding
- application
- analysis
- problem_solving
- hots

Seed the locked v1 cognitive taxonomy:
- remember
- understand
- apply
- analyze
- evaluate

Taxonomies are versioned/configurable. Additional levels or aliases may be added later only through explicit versioned configuration; do not silently promote extra labels to official v1 values.

## Core result contract

Every validator result must be machine-readable and auditable. Minimum shape:

```text
validator_id
validator_version
status = pass | fail | warn | not_applicable | review_required
rule_codes[]
target
observed
evidence[]
policy/source references
input entity references
created_at
```

A free-text explanation may accompany the structured result but cannot be the only evidence.

## Task list

D6-01 — Freeze the Day 6 requirements map  
Map every locked Day 6 capability to implementation/tests and record exclusions for Days 7–10+. Acceptance: no RAG, LangGraph, question generation, exam planner, diagnostic distractor, root-cause learner logic or public product UI is pulled forward.

D6-02 — Establish the generic validator architecture  
Create a framework-independent validator protocol/service boundary rather than subject/board-specific functions. Acceptance: validators can be registered/composed by stable ID/version and tested without FastAPI, RAG or agents.

D6-03 — Add versioned taxonomy registry  
Persist/configure cognitive levels, competencies and relevant educational-quality rule sets with stable IDs, aliases, active/superseded versions and audit metadata. Acceptance: unchanged reload is idempotent; historical versions remain queryable.

D6-04 — Implement locked cognitive taxonomy validation  
Validate only the frozen v1 cognitive values and explicit aliases. Acceptance: unknown values fail/review rather than being silently normalized to a different level.

D6-05 — Implement locked competency taxonomy validation  
Validate Knowledge, Conceptual Understanding, Application, Analysis, Problem Solving and HOTS tags. Acceptance: duplicate, contradictory, unknown or empty competency sets are handled deterministically.

D6-06 — Validate source-backed learning-outcome references  
A question/item claiming a learning outcome must reference an existing outcome in the correct curriculum/version/scope. Acceptance: wrong version, subject, grade/year, medium or superseded/unapproved binding fails closed.

D6-07 — Validate competency references against curriculum evidence  
Where a competency is source-backed, ensure the referenced competency is valid for the supplied framework/curriculum context. Acceptance: generic taxonomy tagging remains distinct from claims of official board/framework competency mapping.

D6-08 — Add cognitive-demand evidence model  
Represent why an item is classified at a cognitive level using structured signals such as recall, interpretation, application, multi-step reasoning, comparison/evaluation and justification requirements. Acceptance: classification evidence is inspectable; labels are not self-attested booleans.

D6-09 — Validate target versus observed cognitive level  
Compare declared target cognitive level with structured observed-demand evidence. Acceptance: clear mismatches fail/warn according to configured policy; uncertain cases return review_required, not fabricated certainty.

D6-10 — Validate target versus observed cognitive level (per item)  
Compare declared target cognitive level with structured observed-demand evidence on each canonical item. Acceptance: clear mismatches fail/warn according to configured policy; uncertain cases return review_required. Paper-level cognitive/competency percentage distribution is **Day 10**, not Day 6.

D6-11 — Add design-time difficulty profile  
Represent difficulty as versioned design-time evidence rather than an empirical learner-performance claim. Initial signals may include cognitive demand, prerequisite depth, step count, abstraction, computation load, language load and expected time band. Acceptance: observed/student-calibrated difficulty is not claimed without data.

D6-12 — Validate declared difficulty against profile  
Compare declared difficulty to structured difficulty signals and policy thresholds. Acceptance: mismatch produces rule-coded evidence; subject-specific heuristics stay in policy/configuration, not generic branching.

D6-13 — Add grade/age appropriateness contract  
Validate supplied learner/grade age-band metadata, language complexity flags, sensitive-context flags and prerequisite expectations. Acceptance: when an authoritative age mapping is unavailable, return unknown/review_required rather than inventing one.

D6-14 — Add language/clarity quality checks  
Implement deterministic structural checks for incomplete stems, malformed options, empty prompts, excessive undefined references, unsupported notation metadata and other measurable clarity defects. Acceptance: no LLM is required to run the Day 6 core suite.

D6-15 — Add educational-quality rule pack  
Provide versioned rules for alignment, clarity, scope, cognitive appropriateness, unnecessary trick wording, answerability metadata, explanation/rubric presence when required and internal consistency. Acceptance: each rule produces a stable code and evidence.

D6-16 — Add rubric schema for subjective items  
Support criteria, criterion weights/points, performance levels, descriptors and outcome/competency links. Acceptance: rubric is canonical JSON/domain data and remains independent of React presentation.

D6-17 — Validate rubric integrity  
Check point totals, duplicate criteria, invalid ranges, missing descriptors, impossible thresholds, inconsistent performance ordering and unresolved criterion links. Acceptance: invalid rubric cannot be marked approved.

D6-18 — Add policy registry and versions  
Represent global education/safety policy, country/board policy, curriculum/exam constraints and institution policy overlays as versioned records/configuration with provenance. Acceptance: policy source/version used by a result is inspectable.

D6-19 — Implement deterministic policy precedence  
Official/higher-authority constraints cannot be weakened by lower-level configuration. Institution overrides may tighten or specialize allowed behavior but cannot make an official prohibition/rule disappear. Acceptance: precedence is tested with conflicting fixtures.

D6-20 — Add institution-override boundary  
Provide generic institution policy overrides without institution-specific branches in validators. Acceptance: override applicability is tenant/institution scoped and cannot leak across institutions.

D6-21 — Add bias/fairness/safety rule framework  
Support configurable rule codes for protected-trait stereotyping, demeaning language, unsafe instructional content, unnecessary sensitive personal data, and other educational safety constraints. Acceptance: core implementation is rule/policy driven and records review_required where deterministic certainty is insufficient.

D6-22 — Preserve curriculum/exam/source separation  
A curriculum outcome, exam evidence, institution preference and educational-quality rule must remain distinguishable. Acceptance: a soft preference cannot masquerade as an official curriculum/exam rule.

D6-23 — Bind validation evidence to exact versions  
Every result must reference exact validator/taxonomy/policy versions and relevant SourceRevision/entity IDs. Acceptance: later policy updates do not retroactively change historical validation records.

D6-24 — Implement composed validation runs  
Create a ValidationRun/aggregate result capable of executing selected validators and returning overall pass/fail/review_required according to explicit policy. Acceptance: one failing mandatory validator cannot be hidden by average scores.

D6-25 — Add severity and blocking semantics  
Rules declare severity/blocking behavior through versioned policy, not ad hoc caller interpretation. Acceptance: mandatory official/safety failures block; advisory quality warnings remain visible but distinct.

D6-26 — Add evidence/explanation output  
Return concise user-facing explanation plus structured machine evidence. Acceptance: explanations cite exact rule codes and entity/policy references; no unsupported claim that an LLM reviewed the item.

D6-27 — Persist validation/audit history  
Store run ID, input identity/hash, validator versions, results, timestamps and actor/tenant context where persistence is used. Acceptance: reruns can be compared and historical decisions remain reproducible.

D6-28 — Enforce deterministic/idempotent behavior  
Same canonical input plus same rule/taxonomy/policy versions must produce the same deterministic core result. Acceptance: ordering, duplicate metadata and repeated execution do not change outcomes unexpectedly.

D6-29 — Add clean internal service/CLI interfaces  
Provide engineering calls to validate one canonical item, exercise cognitive-progression primitives, and inspect rule/policy provenance. Acceptance: no public REST contract is required yet; services remain callable directly in tests. Supplied-set paper distribution validation is Day 10.

D6-30 — Add positive fixtures  
Cover CBSE and Telangana-scoped examples using synthetic/non-copyrighted item text with real entity/source references where appropriate. Acceptance: fixtures clearly distinguish synthetic question content from official curriculum evidence.

D6-31 — Add adversarial fixtures  
Cover wrong curriculum version, wrong grade/medium/subject, invalid outcome, unsupported competency, cognitive mismatch, invalid progression, invalid difficulty, broken rubric, conflicting policies, cross-tenant override, unsafe/bias rule violations and unknown/review states.

D6-32 — Preserve SQLite/PostgreSQL compatibility  
Any persistence additions work locally on SQLite and compile/operate cleanly for PostgreSQL conventions. Acceptance: no SQLite-only JSON/constraint behavior without portable handling.

D6-33 — Preserve migration safety  
If schema changes are required, add a new migration after the current head and test upgrade → downgrade → re-upgrade, populated-data preservation, failure rollback and `alembic check`. Issued migrations remain immutable.

D6-34 — Run full regression on exact candidate  
Run complete backend tests, Ruff, mypy, frontend typecheck/build, migrations, PostgreSQL DDL compilation, Compose/API smoke and all Day 3–5 verification gates applicable to the branch. D5-DS01 remains deferred exactly as approved and must not be rewritten green.

D6-35 — Deliver Founder Day 6 verification  
Provide a deterministic script/report demonstrating: valid item passes; LO/version mismatch fails; inactive SourceRevision cannot authorize LO; missing/wrong medium handled; cognitive mismatch is caught; difficulty evidence is shown; authoritative age mismatch caught; rubric defect fails; policy precedence prevents an institution override weakening an official rule; foreign tenant override ignored without failing valid tenant items; bias/safety rule triggers (stem cannot be bypassed by supplemental safety text); cognitive progression valid/invalid behavior; structural option defects; provenance shows exact validator/taxonomy/policy/quality/safety/source versions.

D6-36 — Deliver Day 6 evidence map and stop gate  
Map D6-01…D6-36 to code/tests/evidence, exact head SHA and CI run. List review-required limitations explicitly. Founder approval is separate. Stop before Day 7.

## Founder acceptance demonstration

The Day 6 handoff must show, at minimum:

```text
canonical assessment item
  -> curriculum/version/LO validation
  -> competency validation
  -> cognitive-level validation
  -> difficulty validation
  -> age/grade + educational-quality validation
  -> rubric validation when applicable
  -> bias/safety + policy precedence
  -> structured ValidationRun
  -> exact provenance / rule codes
```

Paper-level cognitive/competency distribution for supplied item sets is demonstrated on **Day 10** (prerequisite diagnostics and blueprint allocation). Day 6 demonstrates per-item validation and explicit cognitive-progression primitives only.

No assessment generation is required for this demonstration.

## Completion gate

Day 6 engineering may be called complete only when:
- D6-01…D6-36 are evidenced;
- validator behavior is deterministic on fixed versions;
- policy precedence is fail-closed;
- curriculum/source provenance remains exact;
- rubric invariants and per-item cognitive-progression primitives are enforced;
- SQLite/PostgreSQL/migration/full regression gates are green;
- Day 5 deferred D5-DS01 remains open and unchanged in meaning;
- independent review has no unresolved blocker/major finding for the delivered head.

## Explicit exclusions

Day 6 does not implement:
- AnythingLLM, embeddings, semantic retrieval or RAG (Day 7);
- LangGraph author/solver/reviewer/repair workflow (Day 8);
- misconception-driven distractor generation (Day 9);
- prerequisite/root-cause diagnostic engine (Day 10);
- JEE/CUET/CLAT/other ExamPack paper planners;
- learner adaptive remediation;
- public REST/MCP product contracts;
- final React product surfaces.
