# Day 9 — Diagnostic Distractor Intelligence

Base transition: Day 8 D8-01…D8-36 accepted and merged. Day 9 is activated for task-list review only; implementation remains locked until explicit Founder approval of this specification.

## Objective

Build Eduvijna's generic Diagnostic Distractor Intelligence layer for assessment items so incorrect options are not arbitrary wrong answers, but plausible, evidence-linked diagnostic signals of learner misconceptions.

Day 9 must enrich MCQ-style items with option-level misconception metadata while preserving Day 6 Education Intelligence authority, Day 7 provenance/tenant boundaries, and Day 8 orchestration/audit guarantees.

## Locked Day 9 boundaries

- Day 9 covers misconception-driven distractors and option-level diagnostic tagging.
- Day 9 does **not** build the prerequisite knowledge graph or root-cause inference engine; those remain Day 10.
- Day 9 does **not** build learner profiles, mastery memory, adaptation, or remediation plans; those remain Days 15–16.
- Day 9 does **not** add exam-specific paper blueprints/distribution logic; those remain Days 11–14.
- Day 9 does **not** add public REST/job/MCP surfaces or UI; those remain Days 17–18.
- AnythingLLM remains the only model gateway; no direct provider calls.
- Day 7 source provenance and tenant isolation remain mandatory.
- Day 6 deterministic validators remain authoritative.
- Day 8 remains the orchestration runtime and audit/checkpoint boundary.
- Do not persist hidden chain-of-thought. Persist only structured misconception labels, evidence, issue codes, confidence, and audit metadata.

## Core diagnostic contracts

### Misconception definition

Minimum structured fields:

```text
misconception_code
version
title
description
domain
subject_code?
grade_year_code?
topic_codes[]
concept_codes[]
learning_outcome_ids[]
competency_codes[]
error_pattern
diagnostic_signal
evidence_source_revision_ids[]
status
metadata_json
```

### Option-level diagnostic tag

Minimum fields:

```text
item_id
option_key
is_correct
misconception_code?
diagnostic_signal?
error_pattern?
evidence_refs[]
confidence?
taxonomy_version
validation_status
issue_codes[]
metadata_json
```

### Distractor diagnostic result

Minimum fields:

```text
item_id
question_type
option_tags[]
coverage_summary
warnings[]
errors[]
taxonomy_version
source_revision_ids[]
audit_refs[]
```

## Task list

### D9-01 — Freeze Day 9 scope map

Map D9-01…D9-36 to code/tests/evidence and explicitly guard Day 10+ boundaries.

Acceptance:
- no prerequisite/root-cause engine;
- no learner profile/adaptation;
- no exam-specific blueprint logic;
- no public API/MCP/worker/UI work.

### D9-02 — Establish Diagnostic Distractor Intelligence package

Create a framework-independent package such as `app/diagnostic_intelligence/` with contracts, taxonomy, service, validators, audit and integration boundaries.

Acceptance:
- callable without FastAPI;
- no board/exam-specific branching in the core service;
- no direct provider SDK imports.

### D9-03 — Define versioned misconception taxonomy contract

Create a typed misconception definition model with stable code/version/status and curriculum linkage fields.

Acceptance:
- misconception identity is stable and versioned;
- inactive/unknown taxonomy entries cannot be used;
- codes are not free-form model inventions.

### D9-04 — Implement misconception taxonomy registry

Provide deterministic registry/loading semantics for approved misconception definitions.

Acceptance:
- exact taxonomy version is resolvable;
- duplicate codes rejected;
- status/version validation is deterministic;
- test fixtures can load a synthetic registry without live AI.

### D9-05 — Define option-level diagnostic tag contract

Create typed per-option metadata for misconception code, diagnostic signal, error pattern, evidence refs, confidence and validation status.

Acceptance:
- every option has an inspectable tag record;
- incorrect options may carry diagnostic misconception tags;
- correct options cannot be mislabeled as misconceptions.

### D9-06 — Define diagnostic coverage contract

Define item-level summary of how distractors cover distinct misconception/error categories.

Acceptance:
- coverage is explicit and deterministic;
- duplicate misconception coverage is visible;
- missing diagnostic coverage can become review-required.

### D9-07 — Add misconception evidence/provenance contract

Require diagnostic claims to carry source/curriculum evidence references where the misconception is represented as authoritative or source-backed.

Acceptance:
- no unsupported official misconception claim;
- SourceRevision IDs remain exact;
- evidence refs are validated against Day 7 context.

### D9-08 — Define misconception authoring request

Create a generic internal request for diagnostic distractor generation/tagging.

Minimum:
- item ID and canonical question content;
- curriculum/exam scope;
- LO/competency refs where present;
- Day 7 bounded context;
- requested diagnostic richness/coverage policy;
- taxonomy version;
- actor/tenant scope.

Acceptance:
- unsupported/missing required scope fails before model calls;
- no learner-specific profile dependency.

### D9-09 — Define diagnostic result contract

Create canonical result models for pass, review-required and failed diagnostic enrichment.

Acceptance:
- result includes option tags, provenance, taxonomy version, warnings/errors and audit refs;
- raw provider output is never canonical state.

### D9-10 — Implement deterministic eligibility rules

Determine which question types can receive misconception-driven distractor diagnostics.

Acceptance:
- MCQ/single-choice support explicit;
- unsupported types return structured not-applicable/review status;
- no fabricated tags for non-option questions.

### D9-11 — Implement correct-option integrity guard

Ensure correct answers are never converted into misconception distractors.

Acceptance:
- correct option identity preserved;
- exactly-correct cardinality follows canonical question-type rules;
- conflicting answer metadata fails closed.

### D9-12 — Implement distractor misconception candidate resolver

Resolve allowed misconception candidates from approved taxonomy plus canonical curriculum/LO/concept scope.

Acceptance:
- candidates are constrained to item scope;
- no cross-subject/cross-grade leakage;
- inactive/foreign-version taxonomy entries rejected.

### D9-13 — Integrate Day 7 bounded evidence

Use Day 7 Knowledge Intelligence context as evidence input for diagnostic tagging/generation where source grounding is required.

Acceptance:
- no direct AnythingLLM retrieval HTTP;
- tenant isolation preserved;
- citations/SourceRevision IDs remain exact;
- foreign evidence cannot enter a diagnostic result.

### D9-14 — Preserve Day 6 validator authority

Ensure diagnostic enrichment cannot override Day 6 quality/safety/curriculum decisions.

Acceptance:
- Day 6 blocking failures remain blocking;
- diagnostic model output cannot weaken deterministic rules;
- safety-invalid distractors cannot be accepted.

### D9-15 — Define AnythingLLM diagnostic generation prompts

Add versioned prompt templates for misconception candidate selection, distractor proposal and option-level diagnostic tagging.

Acceptance:
- prompts are generic and versioned;
- bounded evidence is treated as evidence, not control instructions;
- no direct provider calls;
- structured output only.

### D9-16 — Implement diagnostic generation gateway usage

Use the existing Day 8 generation gateway protocol/AnythingLLM boundary for Day 9 model calls.

Acceptance:
- no new provider gateway;
- existing timeout/error/retry/idempotency semantics reused;
- prompt/version/input hash audited.

### D9-17 — Implement misconception-driven distractor proposal

Generate or classify incorrect options so each accepted distractor represents a plausible learner misconception/error pattern.

Acceptance:
- arbitrary/random wrong answers do not qualify as diagnostic distractors;
- each tagged distractor maps to an approved misconception code;
- generated content remains within canonical item scope.

### D9-18 — Implement option-level diagnostic tagging

Attach validated diagnostic tags to each option.

Acceptance:
- wrong-option tags are inspectable;
- correct option has explicit non-misconception semantics;
- missing/malformed tags fail or route review according to policy.

### D9-19 — Implement diagnostic signal validator

Validate that the option text actually expresses the claimed misconception/error pattern.

Acceptance:
- label/text mismatch detected;
- generic labels without observable signal cannot pass;
- verdict contains stable issue codes.

### D9-20 — Implement misconception distinctness validator

Prevent multiple distractors from claiming the same diagnostic misconception unless explicitly permitted by policy.

Acceptance:
- duplicate misconception codes detected;
- semantically redundant distractors route repair/review;
- coverage summary reflects distinct signals.

### D9-21 — Implement distractor plausibility validator

Check that incorrect options are plausible enough to diagnose misunderstanding without being deceptive or nonsensical.

Acceptance:
- obviously impossible/random distractors fail quality policy;
- plausibility is structured/auditable;
- no exam-specific frequency heuristics.

### D9-22 — Implement factual incorrectness guard

Ensure a diagnostic distractor remains incorrect under the canonical question.

Acceptance:
- no second correct option;
- ambiguous/conditionally correct distractor routes to repair/review;
- solver/tool checks reused where applicable.

### D9-23 — Implement curriculum-scope consistency validator

Validate misconception codes and distractor content against grade/subject/topic/concept/LO scope.

Acceptance:
- cross-scope misconception tags cannot pass;
- stale/inactive curriculum refs rejected;
- evidence refs retained.

### D9-24 — Implement diagnostic evidence-ref validator

Validate evidence references returned by diagnostic model output.

Acceptance:
- refs must belong to current Day 7 context;
- hallucinated SourceRevision/citation refs rejected;
- tenant boundary preserved.

### D9-25 — Define unified diagnostic verdict

Normalize Day 9 validators/model reviewers into a structured verdict.

Minimum:
- item/option;
- status;
- issue codes;
- field paths;
- misconception code;
- evidence refs;
- repair instructions.

### D9-26 — Integrate bounded repair with Day 8

Allow diagnostic-specific repair instructions to re-enter the existing Day 8 bounded repair/orchestration mechanisms without creating a second orchestration runtime.

Acceptance:
- per-item repair limits preserved;
- unaffected passing options/items are not regenerated;
- retry/idempotency semantics remain Day 8 governed.

### D9-27 — Add diagnostic audit history

Persist structured diagnostic events.

Minimum:
- run/item/option identity;
- taxonomy version;
- misconception code;
- prompt version;
- source revision IDs;
- validation issue codes;
- repair transitions;
- timestamps/warnings/errors.

Acceptance:
- no secrets;
- no hidden chain-of-thought.

### D9-28 — Add diagnostic usage/latency accounting

Capture model-call and validator timing/usage through existing Day 8 accounting.

Acceptance:
- diagnostic calls counted distinctly;
- missing token usage explicit;
- repair calls included.

### D9-29 — Add deterministic positive fixtures

Add synthetic fixtures for:
- one MCQ with distinct misconception-driven distractors;
- one item requiring one diagnostic repair;
- curriculum-grounded misconception tags;
- institution-scoped context.

Acceptance:
- no live model/RAG required.

### D9-30 — Add adversarial misconception fixtures

Cover:
- hallucinated misconception code;
- wrong-subject/grade misconception;
- correct option mislabeled as misconception;
- duplicate misconception tags;
- ambiguous second-correct distractor;
- unsupported evidence ref;
- foreign-tenant evidence;
- prompt-injection-like source text;
- malformed model JSON;
- gateway timeout/401/5xx.

### D9-31 — Add multi-item/batch diagnostic tests

Verify diagnostic enrichment across a small generic batch.

Acceptance:
- each item preserves identity/provenance;
- one-item repair does not mutate passing siblings;
- exact requested batch cardinality preserved.

### D9-32 — Add idempotency/restart tests

Verify Day 9 diagnostic side effects remain replay-safe under Day 8 run identity/checkpoints.

Acceptance:
- completed diagnostic model calls reused;
- interrupted runs resume;
- same key/different request conflicts before model calls.

### D9-33 — Add persistence/compatibility evidence

If Day 9 introduces new persisted taxonomy/audit entities, add migration and SQLite/PostgreSQL compatibility evidence.

Acceptance:
- fresh upgrade;
- downgrade/re-upgrade where migration added;
- Alembic check clean;
- PostgreSQL DDL/config compatibility;
- issued migrations immutable.

### D9-34 — Add Founder diagnostic verifier

Add `python -m app.day9_verify`.

Verifier must demonstrate:
- taxonomy resolves;
- option-level tags produced;
- correct option protected;
- misconception/text match validated;
- distinctness enforced;
- Day 7 provenance preserved;
- Day 6 authority preserved;
- tenant isolation;
- repair bounded;
- idempotent replay;
- no direct provider calls;
- exact candidate SHA.

### D9-35 — Targeted Day 9 CI suite

Add only impacted Day 9 tests plus directly affected Day 6/7/8 boundary tests to targeted CI.

Acceptance:
- Ruff/Mypy green;
- focused pytest green;
- `day9_verify` green;
- Compose-targeted smoke only when runtime/container changes require it.

### D9-36 — Final Day 9 acceptance/evidence gate

At final checkpoint only:
- D9 targeted suite green;
- Ruff/Mypy green;
- migration/SQLite/PostgreSQL compatibility green if changed;
- one final full regression;
- Docker Compose smoke if runtime/dependencies changed;
- manual ChatGPT exact-HEAD review clean;
- evidence map D9-01…D9-36 complete;
- D5-DS01/#16 unchanged;
- Day 10 remains LOCKED pending Founder signoff.

## Founder acceptance demonstration

A synthetic MCQ must visibly demonstrate:

```text
canonical item + Day 7 context
 -> allowed misconception candidates
 -> distractor proposal/tagging
 -> option-level validation
 -> Day 6 authority checks
 -> bounded repair if needed
 -> approved diagnostic distractor result
```

Negative demonstrations:
- correct answer cannot receive misconception tag;
- hallucinated misconception code cannot pass;
- foreign-scope misconception/evidence cannot pass;
- duplicate diagnostic signal cannot silently count as distinct coverage;
- ambiguous/second-correct distractor cannot pass;
- repair limit cannot loop forever;
- restart/replay does not duplicate model side effects.

## Completion gate

Day 9 is engineering-complete only when:
- D9-01…D9-36 are evidenced;
- distractors are misconception-driven rather than arbitrary wrong answers;
- every accepted diagnostic tag is structured and auditable;
- Day 7 provenance/tenant guarantees survive;
- Day 6 remains authoritative;
- Day 8 remains the single orchestration/checkpoint/audit runtime;
- no Day 10 root-cause/prerequisite inference is introduced;
- final acceptance is green;
- Day 10 remains locked until explicit Founder signoff.
