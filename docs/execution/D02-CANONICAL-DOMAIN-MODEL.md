# D02 — Canonical Domain Model

Status: **COMPLETE — FOUNDER SIGNOFF RECEIVED**

Founder signoff signal: **"Day2 signoff provided. Start Day3"**

Previous day: **D01 ENGINEERING COMPLETE / FOUNDER REVIEW**

Next day: **D03 ACTIVE**

## Objective

Establish Eduvijna's canonical, versioned and extensible domain model on top of the D01 platform foundation.

D02 defines the durable data contracts that later curriculum ingestion, examination intelligence, question generation, diagnostics, learner intelligence, APIs and MCP tools will use.

D02 is a **modeling day**, not a content-ingestion or generation day.

## Frozen requirement mapping

The domain model must support the canonical curriculum hierarchy:

```text
Education Framework
  -> Curriculum
  -> Academic Version
  -> Grade / Year
  -> Medium
  -> Subject
  -> Unit
  -> Chapter
  -> Topic
  -> Concept
  -> Learning Outcome
  -> Competency
  -> Prerequisites
```

It must also provide generic structures for:

- CurriculumPack / CurriculumVersion;
- ExamPack / ExamVersion;
- exact and range-based paper-blueprint constraints;
- Source and source provenance;
- Concept prerequisite graph;
- Learning outcomes;
- Competencies;
- Question canonical JSON/data model;
- STEM-capable question assets/LaTeX references;
- option-level diagnostic metadata;
- configurable diagnostic taxonomy;
- test/paper blueprint metadata;
- policy rules and institution overrides;
- arbitrary future curriculum/exam onboarding without core-service rewrites.

## Strict scope boundary

D02 **does not** implement:

- URL/PDF ingestion;
- source checksum/diff workflows beyond model fields;
- official curriculum content population;
- AnythingLLM retrieval;
- LangGraph generation;
- question authoring;
- diagnostic inference;
- learner attempts/mastery;
- JEE/CUET/CLAT/CA/IMAT/EAPCET rules;
- public CRUD APIs;
- admin UI.

Those belong to later approved days.

## Portability requirements

All models must work with:

- local SQLite;
- production PostgreSQL;

through the same SQLAlchemy model layer.

Do not use PostgreSQL-only types such as ARRAY or JSONB in canonical models.

Use portable SQLAlchemy JSON where flexible structured metadata is necessary.

Externally visible identifiers remain UUID-form strings.

## Model package layout

Create a practical structure under `backend/app/models/`, for example:

```text
models/
  mixins.py
  enums.py
  source.py
  curriculum.py
  examination.py
  question.py
  diagnostic.py
  policy.py
```

Create matching Pydantic/domain schemas under `backend/app/schemas/`.

Exact filenames may vary if the resulting organization is cleaner.

## Shared model conventions

Canonical persisted entities should have, where appropriate:

- UUID identifier;
- created_at;
- updated_at;
- active/status fields where lifecycle matters;
- deterministic code/slug fields for stable references;
- human-readable title/name;
- portable JSON metadata field only when strongly justified.

Use database constraints for invariants that can be expressed deterministically.

Avoid implicit magic strings where a stable enum or taxonomy table is required.

## Source / provenance model

Create the canonical Source model needed by Day 3.

Minimum source attributes:

- id;
- source_type;
- title;
- url, optional for uploads/manual sources;
- authority;
- country;
- board_or_exam;
- academic_year;
- effective_date;
- retrieved_at;
- checksum;
- copyright_classification;
- trust_tier;
- anythingllm_workspace, optional;
- lifecycle/status such as staged/active/superseded;
- metadata_json.

Initial source types must accommodate:

- official authority;
- official syllabus;
- official exam bulletin;
- official paper;
- answer key;
- marking scheme;
- sample paper;
- competitive analysis;
- institution content;
- teacher content.

D02 only defines/persists the contract. D03 implements registry/ingestion behavior.

## Curriculum model

### EducationFramework

Represents a governing educational framework.

Minimum:

- code;
- name;
- country;
- description;
- active.

### CurriculumPack

Represents one onboardable curriculum family.

Minimum:

- framework reference, optional where not applicable;
- code;
- name;
- authority;
- country;
- active;
- metadata.

### CurriculumVersion

Represents an academic/versioned release.

Minimum:

- curriculum pack;
- version_code;
- academic_year;
- effective_from;
- effective_to;
- status;
- metadata.

A curriculum version must be uniquely identifiable within its pack.

### CurriculumNode

Use an extensible tree for the curriculum hierarchy rather than hard-coding every country's school structure into separate tables.

Required node types:

- grade_year;
- medium;
- subject;
- unit;
- chapter;
- topic;
- concept.

Minimum fields:

- curriculum_version;
- parent_node, nullable for roots;
- node_type;
- code;
- title;
- sequence;
- description;
- metadata.

Node code must be unique within the relevant version/parent scope.

The design must support both:

- Class/Grade structures;
- First Year / Second Year or other country-specific year structures.

### LearningOutcome

Minimum:

- curriculum_version;
- code;
- text;
- metadata;
- active.

Learning outcomes can attach to one or more curriculum nodes/concepts.

### Competency

Competencies are configurable records, not a permanently hard-coded enum.

Minimum:

- code;
- name;
- description;
- metadata;
- active.

The model must be able to represent current categories such as knowledge, conceptual understanding, application, analysis, problem solving and HOTS without restricting future categories.

### Concept prerequisite graph

Represent directed prerequisite relationships between concept nodes.

Minimum edge data:

- prerequisite_concept;
- target_concept;
- relation_type/default prerequisite;
- strength/weight optional;
- metadata.

Constraints:

- no self-reference;
- duplicate edges rejected.

D02 includes deterministic application-level validation for missing concepts, duplicate prerequisite edges, self-references and prerequisite cycles. The persisted graph remains generic and exam/curriculum agnostic.

## Examination model

### ExamPack

Generic exam family.

Minimum:

- code;
- name;
- authority;
- country;
- active;
- metadata.

No exam-specific branches in generic services.

### ExamVersion

Versioned governing specification.

Minimum:

- exam pack;
- version_code;
- academic_year or cycle;
- effective_from;
- effective_to;
- duration_minutes, optional;
- total_marks, optional;
- status;
- metadata.

An exam version must be uniquely identifiable within its ExamPack.

### ExamSection

Generic ordered section/paper structure.

Minimum:

- exam_version;
- parent_section, nullable;
- code;
- title;
- sequence;
- subject_code, optional;
- duration_minutes, optional;
- metadata.

Nested sections/papers must be possible so future exams can represent paper -> subject -> section structures.

### ExamBlueprintRule

Must support both exact quotas and ranges.

Minimum:

- exam_version and/or section;
- rule_type;
- selector_json;
- exact_count, optional;
- min_count, optional;
- max_count, optional;
- marks_per_question, optional;
- negative_marks, optional;
- metadata.

Validation:

- exact_count cannot be combined with a contradictory min/max;
- min_count <= max_count;
- counts cannot be negative.

The generic model must be able to describe exact patterns such as fixed question counts and range-based patterns without exam-specific table changes.

## Diagnostic taxonomy model

The ARIV diagnostic layer requires a configurable taxonomy rather than prompt-only strings.

Create a hierarchical DiagnosticTaxonomyEntry.

Minimum:

- code;
- name;
- category;
- parent_entry, optional;
- description;
- active;
- metadata.

The initial model must support diagnostic categories including:

- concept mastery;
- formula knowledge;
- calculation;
- misconception;
- application gap;
- reasoning gap;
- prerequisite gap.

Do not seed large content datasets on D02.

## Question canonical model

Create a rich Question entity capable of supporting school assessments and competitive-exam questions.

Minimum core fields:

- id;
- external_code/version marker if useful;
- source/origin type;
- curriculum_version, optional;
- exam_version, optional;
- primary curriculum node/concept, optional;
- question_type;
- stem_text;
- stem_latex, optional;
- solution_text, optional;
- solution_latex, optional;
- answer_json;
- difficulty, optional;
- cognitive_level, optional;
- status;
- metadata;
- created_at/updated_at.

Question types must at minimum accommodate:

- single-choice MCQ;
- multiple-choice MCQ;
- numerical;
- descriptive;
- passage-based;
- multi-part.

### QuestionOption

Minimum:

- question;
- option_key;
- text;
- latex, optional;
- is_correct;
- diagnostic taxonomy reference, optional;
- error_code, optional;
- metadata.

Database constraints should prevent duplicate option keys within a question.

### QuestionAsset

Question schema must support references/data for:

- images;
- SVG;
- graphs;
- tables;
- diagrams;
- passages.

Minimum:

- question;
- asset_type;
- uri/reference, optional;
- alt_text, optional;
- payload_json, optional;
- sequence;
- metadata.

Do not store bulk copyrighted binary source material in Git.

### Question associations

Support many-to-many associations for:

- competencies;
- learning outcomes;
- prerequisite concepts;
- source/provenance.

The canonical Pydantic question contract must explicitly carry curriculum version, exam version,
primary curriculum node, competency, learning-outcome, prerequisite-concept and source/provenance
identifiers. Unknown top-level question-context fields must be rejected rather than silently ignored.

Rubric metadata must use a typed criterion/marks contract rather than unrestricted JSON.

## Test / paper model

Create a canonical test/paper record sufficient for later generation and execution layers.

Minimum concepts:

### TestDefinition

- code;
- title;
- curriculum_version, optional;
- exam_version, optional;
- blueprint_json;
- status;
- metadata.

The blueprint payload must be structurally validated for custom/replica mode, sections,
exact/range counts and topic/difficulty/cognitive/competency distributions instead of accepting
an arbitrary dictionary.

### TestQuestion

- test_definition;
- question;
- sequence;
- section_code, optional;
- marks, optional;
- negative_marks, optional;
- metadata.

No student attempts/scoring history on D02.

## Policy model

Create a generic policy rule structure able to represent precedence such as:

```text
country / official rule
  -> board/exam
  -> institution override
  -> teacher preference
```

Minimum:

- scope_type;
- scope_id or scope_code;
- policy_key;
- value_json;
- priority;
- active;
- effective_from/effective_to;
- source reference, optional;
- metadata.

D02 persists policy records and implements only deterministic precedence/conflict resolution: official hard constraints cannot be silently overridden by institution/teacher preferences, and equal-precedence conflicting rules fail explicitly. Day 6 still owns broader educational and policy-quality validation.

## Provenance associations

Support source provenance for at least:

- CurriculumVersion;
- ExamVersion;
- Question;
- PolicyRule.

Prefer explicit association tables with proper foreign keys over an unenforced generic entity_type/entity_id link.

## Pydantic/domain schemas

Create typed schemas for the main canonical structures sufficient to validate serialization independent of the ORM.

Required validation examples:

- UUID identifiers serialize as strings;
- enum values serialize as stable lowercase strings;
- exact/range blueprint counts validate;
- question difficulty respects the chosen scale;
- a single-choice question cannot declare multiple correct options in its input schema;
- duplicate option keys are rejected;
- self prerequisite edges are rejected;
- policy priority is an integer with deterministic default.

Do not create public CRUD endpoints yet.

## Migration

Add a single coherent D02 Alembic revision after the D01 `system_settings` migration.

The migration must:

- upgrade successfully from D01;
- create all D02 tables, FKs, unique constraints and indexes;
- downgrade cleanly back to D01;
- upgrade again successfully.

SQLite foreign-key-safe upgrade and downgrade behavior is required. Batch table recreation must
not cascade-delete existing question options, assets, provenance links, test membership or other
dependent rows. A populated-database migration regression is mandatory.

## Tests

Add focused tests covering:

### Curriculum
- create framework, pack and version;
- create hierarchy nodes through concept;
- attach learning outcome;
- attach competency;
- create prerequisite edge;
- reject duplicate prerequisite edge/self-reference at the appropriate layer.

### Examination
- create ExamPack/ExamVersion/sections;
- persist an exact-count blueprint rule;
- persist a range-count blueprint rule;
- validate invalid ranges.

### Source
- persist an official source record with provenance metadata;
- source type/trust/status serialization.

### Question
- persist a question;
- options;
- diagnostic tag reference;
- asset;
- competency/outcome/prerequisite/source links;
- schema validation for single-choice correctness and duplicate option keys.

### Test/paper
- create TestDefinition;
- attach ordered questions.

### Policy
- persist country/board/institution-style policy records;
- deterministic priority values.

### Portability
- all D02 tests execute on SQLite without PostgreSQL-only types;
- SQLAlchemy can compile/create the model metadata using the PostgreSQL dialect without requiring a running PostgreSQL service.

### Migration
- D01 -> D02 upgrade;
- D02 -> D01 downgrade;
- D01 -> D02 re-upgrade.

## Optional verification endpoint

A small read-only endpoint such as:

`GET /api/v1/system/domain-model`

may return only domain schema/version metadata for Founder verification.

Do not expose D02 CRUD APIs.

## Founder acceptance

Founder should not need to inspect dozens of tables manually.

D02 handoff must include:

1. `make test` is green.
2. Migration round trip is green.
3. A documented domain-model verification command/script prints a synthetic sample showing:
   - curriculum pack/version;
   - hierarchy ending in concept;
   - prerequisite relation;
   - learning outcome and competency;
   - generic exam pack/version;
   - exact and range blueprint rules;
   - question/options/diagnostic metadata;
   - source provenance;
   - test definition;
   - institution policy override.
4. No real JEE/CBSE/etc. content is required yet.
5. D03 remains locked.

## Definition of Done

D02 is ready for Founder review only when:

- [ ] D01 remains green;
- [ ] canonical Source model exists;
- [ ] EducationFramework exists;
- [ ] CurriculumPack/Version exists;
- [ ] curriculum hierarchy tree exists through concept;
- [ ] learning outcomes exist;
- [ ] configurable competencies exist;
- [ ] prerequisite graph persists and missing/duplicate/self/cyclic prerequisite structures are rejected;
- [ ] ExamPack/Version exists;
- [ ] nested exam sections exist;
- [ ] exact/range blueprint rules validate;
- [ ] diagnostic taxonomy model exists;
- [ ] rich Question/Option/Asset models exist;
- [ ] question competency/outcome/prerequisite/source associations exist;
- [ ] TestDefinition/TestQuestion exists;
- [ ] policy records/precedence fields and deterministic hard-rule resolution exist;
- [ ] CurriculumVersion/ExamVersion/Question/Policy source provenance is supported;
- [ ] Organization/Institution/Teacher/Learner/Admin/API-client ownership models exist with enforced foreign keys and cross-tenant ownership consistency;
- [ ] age/grade applicability and a typed rubric contract are represented in the canonical question contract;
- [ ] canonical question context/provenance identifiers survive validation/serialization;
- [ ] paper blueprint custom/replica, section and distribution structures validate;
- [ ] populated SQLite migrations preserve dependent question data and pass foreign_key_check;
- [ ] Pydantic validation tests pass;
- [ ] SQLite persistence tests pass;
- [ ] PostgreSQL dialect compilation test passes;
- [ ] D02 migration upgrade/downgrade/re-upgrade passes;
- [ ] no exam-specific hard-coded service logic was introduced;
- [ ] no Day-3 ingestion logic was introduced;
- [ ] CI is green;
- [ ] Codex has no unresolved blocker/major D02 findings;
- [ ] Founder verification instructions are committed.

When green, stop at the Founder gate.

**Do not start D03.**
