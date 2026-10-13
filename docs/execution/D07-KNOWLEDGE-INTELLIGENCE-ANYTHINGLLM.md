# Day 7 — Knowledge Intelligence and AnythingLLM

Base: `7c18b0bfa70230491acfed0e3ac9d36e8396b841` on `develop`.

Day 6 is COMPLETE and Founder-approved; final Day 6 correction is integrated into `develop`. Day 7 is ACTIVE. D5-DS01 / issue #16 remains deferred and must not be weakened or rewritten green.

## Objective

Build Eduvijna's Knowledge Intelligence layer and make AnythingLLM the single AI/RAG gateway boundary for retrieval and source-grounded context assembly.

Day 7 must:
- index only governed Eduvijna source revisions;
- preserve exact SourceRevision/entity provenance across ingestion and retrieval;
- prevent cross-tenant knowledge leakage;
- provide deterministic internal Knowledge Intelligence services and test doubles;
- expose structured retrieval/context results for Day 8 LangGraph;
- keep direct model, embedding, vector-store, and provider calls outside Eduvijna business services.

AnythingLLM is a gateway dependency, not the source of truth. GitHub/domain data and Source Intelligence remain authoritative.

## Locked architecture boundary

- AnythingLLM is accessed only through `app/adapters/anythingllm/` (or the existing canonical adapter package if already established).
- No direct OpenAI/Anthropic/Gemini/model-provider calls from education, knowledge, curriculum, question, diagnostic, or learner services.
- No direct vector database or embedding-provider integration outside the AnythingLLM adapter.
- LangGraph orchestration is Day 8 and must not be pulled forward.
- Question generation is not part of Day 7.
- Public REST/MCP product endpoints are Day 17; Day 7 remains internal service/CLI first.
- Public Git must not contain private/bulk copyrighted source bytes.
- Only governed source revisions may enter the knowledge index.

## Core contracts

### Knowledge source binding

Minimum fields:

```text
binding_id
source_id
source_revision_id
source_revision_checksum
anythingllm_workspace
anythingllm_document_id
ownership_scope
index_status
indexed_at
retired_at
retrieval_profile_version
metadata_json
```

### Knowledge retrieval request

Minimum fields:

```text
query_text
organization_id?
institution_id?
teacher_id?
curriculum_version_id?
exam_version_id?
grade_year_code?
medium_code?
subject_code?
topic/concept filters?
source_authority constraints?
top_k
retrieval_profile_version
```

### Knowledge retrieval result

Minimum fields:

```text
query_id
retrieval_profile_version
items[]
  source_id
  source_revision_id
  entity refs
  authority/trust tier
  title/locator
  snippet/context
  score/rank
  workspace/document ids
scope applied
warnings[]
created_at
```

No retrieval result may claim official authority merely because AnythingLLM returned it.

## Task list

### D7-01 — Freeze Day 7 scope map
Map every Day 7 requirement to code/tests/evidence.

Acceptance:
- no LangGraph orchestration;
- no question authoring/generation;
- no public REST/MCP contract;
- no learner adaptation;
- no exam planner;
- no Day 8+ scope leakage.

### D7-02 — Establish generic Knowledge Intelligence package
Create framework-independent internal service boundaries for indexing, retrieval, context assembly, and audit.

Acceptance:
- callable without FastAPI or LangGraph;
- no board/exam/institution-specific branching.

### D7-03 — Define AnythingLLM adapter protocol
Create a typed adapter boundary covering:
- health/capability probe;
- workspace resolution/creation where allowed;
- document upload/index;
- document removal/retirement;
- retrieval/query;
- document/workspace lookup.

Acceptance:
- business services depend on the protocol, not HTTP details.

### D7-04 — Implement AnythingLLM HTTP adapter
Implement the production adapter using environment configuration.

Acceptance:
- base URL and API key from settings only;
- bounded timeout/retry;
- structured error mapping;
- no secrets logged;
- no provider-specific logic escapes the adapter.

### D7-05 — Implement deterministic fake adapter
Provide an in-memory/test adapter.

Acceptance:
- tests do not require live AnythingLLM;
- deterministic retrieval order;
- supports indexing, removal, lookup, and query fixtures.

### D7-06 — AnythingLLM availability semantics
Define explicit states such as:
- available;
- unavailable;
- degraded;
- unauthorized;
- invalid response.

Acceptance:
- knowledge services fail gracefully;
- no application-wide readiness dependency on AnythingLLM;
- unavailable gateway does not corrupt source/index state.

### D7-07 — Versioned retrieval profile
Persist/configure retrieval behavior including:
- top-k defaults;
- score threshold;
- deduplication;
- source-authority preference;
- allowed scopes;
- context-length limits;
- future reranking hooks.

Acceptance:
- profile version appears in query/audit output;
- historical profiles remain loadable.

### D7-08 — Knowledge source binding model
Persist exact mapping from Eduvijna SourceRevision to AnythingLLM workspace/document identity.

Acceptance:
- exact SourceRevision ID + checksum stored;
- unique active binding per index target;
- idempotent repeated indexing.

### D7-09 — Source lifecycle eligibility gate
Before indexing, verify source governance.

Acceptance:
- current indexing requires ACTIVE SourceRevision;
- staged/extracted/validated/approved/rejected/failed/superseded cannot become new active knowledge bindings;
- superseded bindings remain historical but are not active retrieval authority.

### D7-10 — Source ownership/isolation model
Translate Source ownership into knowledge scope:
- global official;
- organization;
- institution;
- teacher.

Acceptance:
- institution/teacher sources never enter global workspaces;
- no cross-tenant binding reuse.

### D7-11 — Workspace resolution strategy
Create deterministic workspace keys from knowledge scope/domain rather than hard-coded names.

Acceptance:
- stable idempotent resolution;
- no institution-name branches;
- workspace identity inspectable in audit data.

### D7-12 — Safe source payload preparation
Build index payload from governed source content/metadata.

Acceptance:
- no private source bytes written to public Git;
- content checksum preserved;
- title/authority/source locator preserved;
- source content treated as untrusted data, not system instructions.

### D7-13 — Prompt-injection/content-instruction boundary
Mark retrieved/indexed source text as evidence content, not executable instructions.

Acceptance:
- adapter/service contract keeps source text separate from system/control instructions;
- synthetic injection fixtures do not alter control metadata.

### D7-14 — Idempotent indexing service
Implement `index_source_revision`.

Acceptance:
- same revision/checksum/profile does not duplicate;
- returns existing binding when already current;
- failed indexing does not mark binding active.

### D7-15 — Replacement/supersession handling
When a new active source revision replaces an old one:
- create/index new binding;
- retire/detach prior active binding only after safe replacement;
- preserve historical mapping.

Acceptance:
- no retrieval window where failed replacement silently removes valid current evidence.

### D7-16 — Index removal/retirement service
Implement safe de-indexing/retirement.

Acceptance:
- explicit state transition;
- remote failure remains retryable;
- audit trail preserved.

### D7-17 — Knowledge retrieval request contract
Define validated scoped request model.

Acceptance:
- query cannot silently omit tenant scope when tenant data may be eligible;
- invalid top_k/filter combinations fail deterministically.

### D7-18 — Scope filter compiler
Compile Eduvijna ownership/curriculum/exam filters into adapter retrieval constraints and local post-filtering.

Acceptance:
- generic;
- exact applied scope returned in result.

### D7-19 — Cross-tenant retrieval isolation
Enforce organization/institution/teacher boundaries before results reach callers.

Acceptance:
- foreign-tenant hit is dropped and audit-visible;
- synthetic adversarial test proves isolation.

### D7-20 — Authority-aware retrieval normalization
Normalize AnythingLLM hits into Eduvijna evidence items.

Acceptance:
- official source, official supporting, analytical, institution, and teacher evidence remain distinct;
- lower authority never masquerades as official.

### D7-21 — Exact SourceRevision validation on retrieval
Every result must resolve back to the indexed SourceRevision/binding.

Acceptance:
- missing/stale/unknown remote document binding is rejected or flagged;
- active current query never fabricates provenance.

### D7-22 — Result deduplication
Deduplicate repeated chunks/documents without losing evidence references.

Acceptance:
- deterministic ordering;
- exact source refs retained.

### D7-23 — Retrieval score/rank semantics
Keep gateway score separate from authority.

Acceptance:
- high similarity does not upgrade source authority;
- ranking output includes both retrieval score and authority metadata.

### D7-24 — Knowledge context pack builder
Build a structured context pack for Day 8.

Minimum output:
- query;
- retrieved evidence;
- exact citations/provenance;
- scope;
- retrieval version;
- warnings;
- bounded text payload.

Acceptance:
- no agent framework dependency;
- deterministic from fixed retrieval result.

### D7-25 — Context budget enforcement
Bound result count/text size.

Acceptance:
- deterministic truncation policy;
- provenance for retained items remains intact;
- overflow is reported, not silently lost.

### D7-26 — Evidence/citation formatter
Create internal source citation labels from exact source/entity refs.

Acceptance:
- citation label cannot exist without resolvable provenance;
- no unsupported official claim.

### D7-27 — Retrieval audit history
Persist query/audit metadata:
- query ID/hash;
- actor/tenant;
- retrieval profile version;
- workspaces queried;
- result source revisions;
- timestamps;
- warnings/errors.

Acceptance:
- no secret/API key storage.

### D7-28 — Failure and retry semantics
Define retryable vs terminal indexing/retrieval failures.

Acceptance:
- bounded retries;
- no duplicate remote uploads after ambiguous retries where idempotency key/binding can resolve state.

### D7-29 — Internal service/CLI
Provide engineering commands to:
- probe AnythingLLM;
- index one eligible synthetic/private fixture source;
- query scoped knowledge;
- inspect provenance/binding;
- retire binding.

Acceptance:
- no public REST required.

### D7-30 — Positive fixtures
Synthetic/non-copyrighted fixtures covering:
- official global source;
- institution source;
- teacher source;
- scoped curriculum metadata.

Acceptance:
- synthetic content is never labeled as official merely because metadata resembles official structure.

### D7-31 — Adversarial fixtures
Cover:
- inactive revision indexing;
- duplicate indexing;
- supersession;
- foreign-tenant workspace/result;
- unknown remote document;
- stale checksum;
- AnythingLLM timeout/401/5xx/malformed response;
- prompt-injection-like source text;
- authority misclassification;
- missing exact retrieval profile;
- excessive context size.

### D7-32 — SQLite/PostgreSQL compatibility
Any persistence additions must work on SQLite and compile cleanly for PostgreSQL.

### D7-33 — Migration safety
Add successor migration only.

Acceptance:
- upgrade -> downgrade -> re-upgrade;
- populated-data preservation where relevant;
- `alembic check`;
- issued migrations immutable.

### D7-34 — Targeted Day 7 test gate
During implementation, run only impacted tests:
- adapter change -> adapter tests;
- indexing/lifecycle change -> knowledge indexing tests;
- retrieval/isolation change -> retrieval tests;
- migration/model change -> migration/PostgreSQL tests;
- Docker/settings change -> targeted config/container smoke.

Do **not** rerun the full historical backend suite for every Day 7 commit.

### D7-35 — Founder Day 7 verifier
Provide `python -m app.day7_verify` demonstrating:
- gateway fake health/probe;
- active revision indexing;
- inactive revision rejection;
- idempotent duplicate indexing;
- tenant isolation;
- exact SourceRevision provenance;
- authority separation;
- deterministic retrieval/context pack;
- unavailable gateway graceful failure;
- retrieval profile version;
- audit persistence.

The verifier must record the exact candidate SHA.

### D7-36 — Final acceptance/evidence gate
At final Day 7 checkpoint only:
- targeted Day 7 suite green;
- Ruff/Mypy relevant scope green;
- migration/PostgreSQL checks green if changed;
- frontend only if changed;
- Compose only if Day 7 container/config changed;
- one full regression before merge;
- independent review has no blocker/P1/major finding, or any Founder-approved external-review exception is explicitly documented;
- evidence map D7-01…D7-36;
- D5-DS01/#16 unchanged;
- Day 8 remains LOCKED pending Founder approval.

## Founder acceptance flow

```text
ACTIVE governed SourceRevision
  -> Knowledge eligibility gate
  -> workspace resolution
  -> AnythingLLM adapter index
  -> persisted exact binding
  -> scoped retrieval request
  -> tenant + authority filtering
  -> exact SourceRevision evidence
  -> deterministic context pack
  -> retrieval audit
```

Negative demonstrations:
- inactive revision cannot index;
- foreign tenant evidence cannot leak;
- unknown/stale AnythingLLM document cannot become trusted evidence;
- lower-authority result cannot be presented as official;
- AnythingLLM outage degrades gracefully.

## Testing policy

Day 7 follows the Founder-approved targeted strategy:
- implementation iterations: impacted tests only;
- no full-suite rerun after every commit;
- full regression once at final acceptance/merge checkpoint;
- successful unaffected jobs are not rerun solely because another targeted check failed.

## Completion gate

Day 7 is engineering-complete only when:
- D7-01…D7-36 are evidenced;
- AnythingLLM remains behind the single adapter boundary;
- active SourceRevision eligibility is enforced;
- tenant isolation is proven;
- retrieval authority/provenance is exact;
- deterministic fake-adapter tests pass;
- live gateway dependency is not required for core CI;
- SQLite/PostgreSQL/migrations remain safe;
- final acceptance checkpoint is green;
- Day 8 remains locked until explicit Founder signoff.
