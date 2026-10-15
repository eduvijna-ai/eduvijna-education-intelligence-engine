# Day 8 — LangGraph Orchestration

Base: `4b12f43fa55a79841c24339674bba649372ac171` on `develop`.

Day 7 is COMPLETE and Founder-approved. Day 8 is ACTIVE, but implementation remains pending Founder approval of this tasklist.

## Objective

Build Eduvijna's generic LangGraph orchestration engine for governed question-authoring workflows:

```text
Request
  -> Curriculum/Exam Resolver
  -> Source/Context Resolver
  -> Generic Generation Planner
  -> Question Author
  -> Independent Solver
  -> Pattern Reviewer
  -> Curriculum Reviewer
  -> Educational Reviewer
  -> Deterministic Validator
  -> Duplicate/Similarity Validator
       FAIL -> Repair -> re-review
  -> Whole-output Validator
  -> Approved Output
```

The graph must consume Day 7 Knowledge Intelligence context and Day 6 Education Intelligence validators without bypassing either domain's governance.

## Locked Day 8 boundaries

- LangGraph is the orchestration runtime.
- AnythingLLM remains Eduvijna's only model/RAG gateway boundary. No direct OpenAI/Anthropic/Gemini/provider calls from graph or business nodes.
- Day 7 `KnowledgeContextPack` / retrieval contracts remain the source-grounding input to author/reviewer nodes.
- Day 6 deterministic education validators remain authoritative for Bloom/competency/LO/rubric/difficulty/age/cognition/quality/safety checks.
- Day 8 may enforce generic requested batch cardinality, but exam-specific replica blueprints, distributions, and JEE exact-count planning remain Day 11+.
- Misconception-driven distractor taxonomy/tagging is Day 9.
- Prerequisite KG/root-cause diagnostics/cognitive distribution engine is Day 10.
- Exam-specific planners/packs are Days 11–14.
- Learner memory/adaptation is Days 15–16.
- Public REST, async durable worker/job API, auth and MCP are Day 17.
- React product surfaces are Day 18.
- No personal learner memory is stored in LangGraph state on Day 8.
- Do not persist hidden chain-of-thought. Persist structured decisions, verdicts, issue codes, evidence refs and audit metadata only.

## Core contracts

### Orchestration request

Minimum fields:

```text
run_id / idempotency_key
generation_mode
requested_count
curriculum_version_id?
exam_version_id?
grade_year_code?
medium_code?
subject_code?
topic/concept refs?
question_type?
marks?
difficulty target?
cognitive target?
competency target?
retrieval_profile_version
max_repairs
actor/tenant scope
metadata_json
```

### Graph state

Minimum state:

```text
run_id
request
resolved_scope
generation_plan
knowledge_context
draft_items
solver_results
review_verdicts
deterministic_validation
duplicate_validation
repair_count_by_item
node_attempts
warnings
errors
status
created_at / updated_at
```

### Structured review verdict

```text
reviewer
item_id
status: pass | repair | reject | review_required
issue_codes[]
field_paths[]
evidence_refs[]
repair_instructions[]
metadata_json
```

### Final orchestration result

```text
run_id
status
requested_count
approved_count
items[]
source_revision_ids[]
retrieval_profile_version
prompt/template versions
repair summary
warnings/errors
audit refs
started_at / completed_at
```

## Task list

### D8-01 — Freeze Day 8 scope map

Map D8-01…D8-36 to code/tests/evidence and explicitly guard Day 9+ boundaries.

Acceptance:
- no diagnostic misconception taxonomy;
- no prerequisite/root-cause engine;
- no exam-specific blueprint logic;
- no learner adaptation;
- no public REST/MCP/async worker implementation;
- no UI work.

### D8-02 — Establish generic orchestration package

Create a framework-independent package such as `app/orchestration/` containing graph state, nodes, routing, audit and service boundaries.

Acceptance:
- callable without FastAPI;
- callable without public API/job worker;
- no board/exam-specific branching in core orchestration.

### D8-03 — Define typed LangGraph state

Create strongly typed/Pydantic-compatible graph state with explicit reducers/update semantics where needed.

Acceptance:
- node inputs/outputs are inspectable;
- no arbitrary mutable global state;
- provenance, warnings and repair counters survive every transition.

### D8-04 — Define model-generation gateway protocol

Create a typed generation/review model port implemented only behind the AnythingLLM adapter boundary.

Acceptance:
- graph nodes depend on protocol/DI, not HTTP/provider SDKs;
- request supports prompt/template version, context, structured-output schema and model settings;
- response exposes parsed content plus usage/latency/gateway request metadata where available.

### D8-05 — Implement AnythingLLM generation adapter

Implement the production Day 8 generation/review call through supported AnythingLLM APIs.

Acceptance:
- URL/key/settings from configuration only;
- no direct provider credential;
- bounded timeout/retry;
- structured invalid/unauthorized/unavailable error mapping;
- no secrets in logs/audits.

### D8-06 — Implement deterministic fake generation gateway

Provide deterministic author/solver/reviewer responses for tests.

Acceptance:
- no live AnythingLLM or model required for core CI;
- fixture responses selectable by scenario;
- call history exposes node/prompt/version/input hashes.

### D8-07 — Versioned prompt/template registry

Create versioned prompt templates for author, solver, pattern review, curriculum review, educational review and repair.

Acceptance:
- prompt version recorded in graph/audit output;
- source text is evidence data, never injected as system/control instructions;
- templates are generic and not exam-specific.

### D8-08 — Orchestration request contract

Validate generation requests and generic constraints.

Acceptance:
- requested_count bounded and positive;
- tenant/curriculum/exam scope validated;
- unsupported combinations fail before model calls;
- max repair limit bounded by policy.

### D8-09 — Orchestration result contract

Define canonical result models for approved, rejected, partially approved and failed runs.

Acceptance:
- exact provenance and graph versions returned;
- no raw provider response becomes the public/internal canonical result.

### D8-10 — Run identity and idempotency contract

Define stable `run_id`, request hash and idempotency behavior.

Acceptance:
- replay of the same completed run cannot create duplicate approved artifacts;
- run identity is short enough for persistent LangGraph thread IDs;
- idempotency remains independent of future Day 17 job IDs.

### D8-11 — LangGraph builder and dependency injection

Build the StateGraph with injected knowledge, generation, validator, duplicate and checkpoint dependencies.

Acceptance:
- deterministic graph topology;
- no singleton/global gateway;
- graph can compile with in-memory/fake dependencies for tests.

### D8-12 — Curriculum/exam resolver node

Resolve supplied canonical curriculum/exam references without introducing exam-specific planning.

Acceptance:
- validates references/status/version;
- returns canonical refs and scope;
- cannot fabricate missing curriculum/exam provenance.

### D8-13 — Source/context resolver node

Call Day 7 Knowledge Intelligence and construct the bounded context used by author/reviewer nodes.

Acceptance:
- uses Day 7 service/contracts, not direct AnythingLLM retrieval HTTP;
- tenant isolation preserved;
- SourceRevision IDs/citations retained;
- retrieval warnings propagate into graph state.

### D8-14 — Generic generation planner node

Turn the request into generic work items.

Acceptance:
- preserves requested_count as a generic cardinality invariant;
- creates deterministic item IDs/slots;
- does not encode JEE/CUET/CLAT/other exam blueprint distributions.

### D8-15 — Question author node

Generate canonical draft questions from resolved constraints and Day 7 context.

Acceptance:
- structured output only;
- exact citations/evidence refs carried forward;
- no unsupported official claims;
- no Day 9 diagnostic distractor tagging.

### D8-16 — Independent solver node

Solve each authored item independently from the author result.

Acceptance:
- solver does not receive author's claimed answer/rationale where avoidable;
- produces structured proposed answer/working/check status;
- discrepancies route to review/repair.

### D8-17 — Deterministic math/tool checking boundary

Provide deterministic verification tools for supported mathematical/logical checks, with SymPy or equivalent deterministic libraries where justified.

Acceptance:
- tool result distinguished from model opinion;
- unsupported symbolic checks return unknown/review-required, not fabricated certainty;
- no arbitrary code execution.

### D8-18 — Pattern reviewer node

Review generic question structure, answerability, option consistency, marks/question-type contract and request constraints.

Acceptance:
- no exam-specific pattern statistics;
- structured issue codes and repair instructions.

### D8-19 — Curriculum reviewer node

Review curriculum/LO/concept alignment against canonical refs and Day 7 evidence.

Acceptance:
- no fabricated LO/competency refs;
- stale/inactive provenance cannot pass;
- review result retains evidence refs.

### D8-20 — Educational reviewer node

Invoke/interpret Day 6 Education Intelligence validation.

Acceptance:
- Day 6 deterministic validation remains authoritative;
- model reviewer cannot weaken blocking Day 6 rules;
- official/institution/teacher precedence preserved.

### D8-21 — Deterministic validator aggregation node

Combine schema, solver/tool, Day 6 and hard business-rule validation into a single structured gate.

Acceptance:
- blocking vs repairable vs review-required is deterministic;
- error codes are stable/testable.

### D8-22 — Duplicate/similarity validation node

Detect exact/near duplicate generation without importing Day 9 diagnostic logic.

Acceptance:
- exact normalized duplicate check deterministic;
- optional similarity service is behind a typed boundary;
- similarity never changes source authority;
- duplicate verdict is auditable.

### D8-23 — Unified review verdict contract

Normalize all reviewer/validator outputs into one verdict schema.

Acceptance:
- each issue has reviewer, issue code, field path and evidence;
- no free-form-only failure path.

### D8-24 — Repair planner node

Build a bounded repair instruction from structured findings.

Acceptance:
- repair prompt receives only necessary failed fields/findings/context;
- already-passing evidence/provenance is preserved where possible;
- repair cannot silently change tenant/scope/version constraints.

### D8-25 — Bounded repair loop/router

Route repairable failures back through author/solver/review deterministically.

Acceptance:
- configurable default repair limit with hard maximum;
- per-item repair count tracked;
- no infinite cycles;
- exhausted items route to reject/review-required.

### D8-26 — Whole-output validator

Validate the final generic batch/run.

Acceptance:
- approved item count equals requested_count when run status is approved;
- duplicate item IDs/content blocked;
- all approved items have valid provenance and final review state;
- exam-specific distribution validation remains Day 11+.

### D8-27 — Terminal state and error taxonomy

Define statuses such as:
`planning`, `authoring`, `solving`, `reviewing`, `repairing`, `review_required`, `completed`, `failed`.

Acceptance:
- retryable gateway failure distinguished from terminal validation rejection;
- node exceptions map to structured run failure;
- partial state remains inspectable.

### D8-28 — LangGraph checkpoint persistence abstraction

Add checkpointer wiring for local and production modes.

Acceptance:
- SQLite-backed persistent checkpointer for local development/tests where appropriate;
- PostgreSQL-backed checkpointer/config for production;
- in-memory checkpointer only for isolated tests;
- no learner long-term memory Store introduced on Day 8.

### D8-29 — Resume/restart semantics

Support resuming an interrupted graph from persisted checkpoints.

Acceptance:
- completed model/tool side effects are not blindly repeated;
- run/thread ID reloads graph state;
- deterministic fixture proves restart after an intermediate node.

### D8-30 — Human-in-the-loop interrupt/escalation hook

Provide a generic interrupt point for review-required/max-repair cases, without building UI.

Acceptance:
- state can pause with structured review payload;
- approved/rejected/manual-update resume path testable;
- no Day 18 UI dependency.

### D8-31 — Graph execution audit history

Persist structured run/node events.

Minimum:
- run ID/request hash;
- node name/status/attempt;
- prompt/template version;
- source revision IDs;
- gateway request ID if available;
- validator/reviewer issue codes;
- repair transitions;
- timestamps/warnings/errors.

Acceptance:
- no API keys/secrets;
- no hidden chain-of-thought.

### D8-32 — Usage/latency accounting

Capture available AI usage and execution metrics.

Acceptance:
- per-node latency;
- model/gateway usage metadata where returned;
- model-call count and repair count;
- missing usage is explicit, not fabricated.

### D8-33 — Positive orchestration fixtures

Add deterministic fixtures for:
- one clean question first-pass approval;
- one question repaired then approved;
- small generic multi-item batch;
- curriculum-grounded and institution-scoped context;
- checkpoint resume.

Acceptance:
- no live model/RAG required.

### D8-34 — Adversarial orchestration fixtures

Cover:
- malformed model JSON;
- author/solver disagreement;
- hallucinated provenance;
- foreign-tenant context attempt;
- blocking Day 6 validation;
- prompt-injection-like evidence;
- duplicate output;
- gateway timeout/401/5xx;
- repair exhaustion;
- interrupted/resumed run;
- idempotent replay.

### D8-35 — Targeted Day 8 tests and Founder verifier

Add impacted test modules and `python -m app.day8_verify`.

Verifier must demonstrate:
- graph compiles;
- Day 7 context enters graph with exact provenance;
- author -> solver -> reviewers -> deterministic validator path;
- repair loop succeeds for repairable fixture;
- blocking fixture cannot be approved;
- tenant isolation;
- bounded repair exhaustion;
- checkpoint/resume;
- idempotent run replay;
- no direct provider calls;
- exact candidate SHA.

### D8-36 — Final Day 8 acceptance/evidence gate

At final checkpoint only:
- D8 targeted suite green;
- Ruff/Mypy changed scope green;
- checkpoint persistence/migration tests green if schema/dependency changed;
- SQLite/PostgreSQL compatibility green;
- one final full regression;
- Docker Compose smoke if dependencies/container config changed;
- manual ChatGPT code review clean under Founder workflow;
- evidence map D8-01…D8-36 complete;
- D5-DS01/#16 unchanged;
- Day 9 remains LOCKED pending Founder signoff.

## Testing policy

Follow the Founder-approved manual workflow:

```text
ChatGPT requirement handoff
  -> Cursor implementation
  -> Founder manually notifies ChatGPT
  -> ChatGPT exact-HEAD code review
  -> repair handoff only if needed
  -> repeat until clean
  -> final acceptance gate
```

During implementation:
- run impacted Day 8 tests only;
- do not run full historical pytest after every commit;
- early broad regression only for shared core, schema/migration, LangGraph/checkpointer dependency, or test-infrastructure changes;
- full regression once at final acceptance.

## Founder acceptance demonstration

A synthetic grounded request must visibly execute:

```text
request
 -> resolve canonical scope
 -> Day 7 context pack
 -> author
 -> independent solver
 -> reviewers
 -> Day 6 deterministic validation
 -> repair when needed
 -> final whole-output validation
 -> approved structured output
```

Negative demonstrations:
- foreign tenant context never reaches approved output;
- hallucinated SourceRevision/citation is rejected;
- blocking deterministic validation cannot be overridden by a model;
- repair limit cannot loop forever;
- interrupted graph resumes from checkpoint;
- malformed/unavailable gateway fails safely.

## Completion gate

Day 8 is engineering-complete only when:
- D8-01…D8-36 are evidenced;
- LangGraph orchestration is generic and auditable;
- AnythingLLM remains the only model/RAG gateway;
- Day 7 provenance/tenant guarantees survive graph execution;
- Day 6 deterministic validators remain authoritative;
- repair loops are bounded;
- graph state is persistent/restartable;
- no hidden chain-of-thought is stored;
- final acceptance is green;
- Day 9 stays locked until explicit Founder signoff.
