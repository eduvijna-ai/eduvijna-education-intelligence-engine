# D03 — Source Intelligence

Status: **ACTIVE**

Founder approval to start: **GRANTED**

Previous day: **D02 COMPLETE**

Next day: **D04 LOCKED**

## Objective

Build Eduvijna's revision-aware Source Intelligence layer: registry, private ingestion,
checksums, extraction, provenance, diffing, lifecycle control, approval and activation.

A source fetch or upload must never silently replace the active source revision.

## Scope

### D3-01 — Service boundaries
Registry, storage, extraction, verification, diff, lifecycle and provenance are separate,
testable components.

### D3-02 — Source Registry
Support the frozen source classes: official authority, official syllabus, official exam bulletin,
official paper, answer key, marking scheme, sample paper, competitive analysis, institution
content and teacher content.

### D3-03 — Governance hierarchy
Official-primary evidence is authoritative for hard rules. Official supporting evidence,
competitive analysis, institution content and teacher content have progressively softer roles.
A non-official source cannot be attached as provenance for a hard official policy.

### D3-04 — Immutable revisions
Each content snapshot has a source ID, revision number, SHA-256 checksum, ingestion method,
content type, byte size, retrieval timestamp, storage reference, extraction state and lifecycle.

### D3-05 — Private storage
Runtime documents live under SOURCE_STORAGE_DIR (default data/private/sources), outside Git.

### D3-06…D3-10 — Intake methods
Support URL, PDF, DOCX, CSV, JSON and manual metadata fallback.

### D3-11 — Duplicate detection
The same source + checksum resolves to the existing revision rather than creating a duplicate.

### D3-12 — Provenance metadata
Retain authority, country, board/exam, academic year, effective date, copyright classification,
trust tier and AnythingLLM workspace/document references.

### D3-13 — Deterministic extraction
Day 3 performs document parsing/text normalization. OCR and live AI/RAG extraction are not
claimed here; live AnythingLLM work remains Day 7.

### D3-14 — Validation
Validate checksum/storage integrity, extraction, governance and required diff creation.

### D3-15 — Diff engine
Persist non-copying diff statistics and changed ranges between a candidate and the active revision.

### D3-16 — Pattern drift candidate
Changed official source content is flagged for review, not automatically interpreted as a new exam
or curriculum rule.

### D3-17 — Lifecycle
staged -> extracted -> validated -> approved -> active, with rejected/failed/superseded outcomes.
Illegal transitions fail.

### D3-18 — Transactional activation
Exactly one active revision is allowed per logical source. Replacement activation supersedes the
previous active revision in the same database transaction.

### D3-19 — No silent update
Ingest, extract, diff and validate operations cannot change the active source checksum/revision.

### D3-20 — Revision-aware provenance
SourceRevision links are available for CurriculumVersion, ExamVersion, Question and PolicyRule.

### D3-21 — Copyright/data safety
No source-document dumps are committed to Git. Tests use synthetic content.

### D3-22 — URL/file safety
Only public HTTP/HTTPS targets are permitted. Block embedded credentials, localhost/private/link-
local/reserved targets, unsafe redirects, oversized responses and storage path traversal.

### D3-23 — Audit events
Persist source register/ingest/extract/diff/validate/approve/activate/supersede/reject/retry events.

### D3-24 — Structured logging
Operational logs contain source/revision/request IDs and outcomes, never complete documents or keys.

### D3-25 — Retry contract
Extraction/validation failures are explicit and retryable without creating uncontrolled duplicate
content or modifying the active source.

### D3-26 — Internal engineering CLI
python -m app.source_cli exposes register, ingest, inspect, extract, diff, validate, approve,
activate, reject and retry operations. Public CRUD APIs remain later scope.

### D3-27 — Database portability
Canonical models use portable SQLAlchemy types and compile for PostgreSQL while running locally
on SQLite.

### D3-28 — Migration safety
Revision 20261002_0005 upgrades/downgrades/re-upgrades without modifying Day-1/Day-2 rows.
A failed Day-3 migration must not advance the previous migration revision.

### D3-29 — Intake tests
Synthetic tests cover URL, PDF, DOCX, CSV, JSON and manual metadata.

### D3-30 — Lifecycle/adversarial tests
Cover duplicate checksum, corrupt documents, invalid transitions, approval gating, candidate drift,
single-active revision and preservation of the existing active source.

### D3-31 — Governance/provenance tests
Verify trust classification and revision-aware persistence. Competitive evidence cannot support a
hard official policy.

### D3-32 — Founder verification
make source-verify demonstrates first activation, changed candidate remaining staged/reviewed,
pattern-drift flagging and approved replacement/supersession.

### D3-33 — Regression
Day-1/Day-2 backend tests, Ruff, Mypy, frontend typecheck/build, migration checks and Compose smoke
remain green.

### D3-34 — Handoff
Deliver exact tested commit, task/evidence mapping, Founder UAT instructions and matching source
handoff/checksum. Stop before Day 4.

## Strict boundaries

D03 does not populate NCF/NCERT/CBSE/Telangana content, implement education-quality validators,
enable live AnythingLLM RAG, implement LangGraph generation, expose public Source CRUD APIs,
or build the final React Admin Source UI.

## Definition of Done

- [ ] D3-01 through D3-34 are mapped to code/tests/evidence.
- [ ] all six ingestion methods are tested with synthetic/mocked inputs.
- [ ] unchanged checksums do not create new revisions.
- [ ] changed official content remains a candidate until explicit approval and activation.
- [ ] exactly one active revision is enforced.
- [ ] revision-aware provenance persists.
- [ ] private storage and URL/file safety tests pass.
- [ ] audit events and structured source logs exist.
- [ ] SQLite migration preservation and failure-state tests pass.
- [ ] PostgreSQL dialect compilation passes.
- [ ] make source-verify passes.
- [ ] full existing regression and Compose smoke pass.
- [ ] no Day-4 implementation is present.
- [ ] Founder verification instructions are committed.

When all checks are green, stop at Founder review. Do not start D04.
