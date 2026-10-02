# D03 — Source Intelligence Completion Report

Status: **FOUNDER REVIEW**

Day 4: **LOCKED**

This report maps the approved Day-3 checklist to the implementation and deterministic evidence.
Founder approval is not inferred from CI.

| Task | Implementation / evidence |
|---|---|
| D3-01 | `app/source_intelligence/` separates storage, URL security/fetch, extraction and lifecycle service concerns. |
| D3-02 | Existing canonical `Source` registry supports all frozen source classes; Day 3 adds revision-aware behavior. |
| D3-03 | Source type/trust-tier governance is enforced; hard official policy provenance requires official-primary evidence. |
| D3-04 | `SourceRevision` stores immutable revision number, checksum, method, MIME, byte size, retrieval/storage/extraction/lifecycle metadata. |
| D3-05 | `LocalSourceStorage` writes beneath `SOURCE_STORAGE_DIR`; `data/private/` remains Git-excluded. |
| D3-06 | `SourceUrlFetcher` supports bounded HTTP/HTTPS URL ingestion with redirect and actual-peer validation. |
| D3-07 | PDF upload/extraction uses pypdf; corrupt/encrypted/no-text outcomes are explicit. OCR is intentionally outside Day 3. |
| D3-08 | DOCX upload/extraction uses python-docx; corrupt/no-text outcomes are explicit. |
| D3-09 | CSV and JSON ingestion validates/parses and normalizes structured content. |
| D3-10 | Manual metadata revisions support authority-site fallback without code changes. |
| D3-11 | SHA-256 plus source-scoped uniqueness prevents duplicate revisions for unchanged content. |
| D3-12 | Source/revision records preserve authority, country, board/exam, academic year, effective/retrieval data, copyright, trust and AnythingLLM reference fields. |
| D3-13 | Deterministic parser/normalizer interface is implemented. Live AnythingLLM/RAG/AI extraction remains Day 7. |
| D3-14 | Validation covers checksum format, stored-byte checksum/size, extraction, source governance and current diff. |
| D3-15 | `SourceDiff` persists checksum/metadata change summaries, similarity and changed ranges without copying full source text into diff records. |
| D3-16 | Changed official content is marked `pattern_drift_candidate` for review only. |
| D3-17 | Service methods enforce staged/extracted/validated/approved/active plus failed/rejected/superseded transitions. |
| D3-18 | Activation is transactional; one active revision per source is enforced by database invariant and rollback regression. |
| D3-19 | Ingestion/extraction/diff/validation do not modify active source identity; acceptance test verifies this. |
| D3-20 | Revision-aware provenance tables link SourceRevision to CurriculumVersion, ExamVersion, Question and PolicyRule. |
| D3-21 | Runtime source bytes remain private; synthetic fixtures are used in tests; copyrighted dumps are not committed. |
| D3-22 | URL security blocks unsafe schemes, embedded credentials, local/private/link-local/reserved resolution, private redirects, DNS-rebound private peers and oversized responses; storage blocks traversal. |
| D3-23 | Persistent audit events cover register, ingest/failure, extract/failure, diff/refresh, checksum verification, validate, approve, activate, supersede, reject, retry and provenance linking. |
| D3-24 | Structured source logs contain identifiers/outcomes and are emitted only after successful DB commit; tests reject false success logs and full document content in audit payloads. |
| D3-25 | Network/extraction/validation failures are explicit; retries preserve active state and do not create uncontrolled duplicate revisions. |
| D3-26 | `python -m app.source_cli` provides internal register/ingest/inspect/extract/diff/validate/approve/activate/reject/retry operations. |
| D3-27 | Day-3 models use portable SQLAlchemy types; full metadata plus dedicated Day-3 tables compile using the PostgreSQL dialect. |
| D3-28 | Alembic revision `20261002_0005` preserves Day-1/Day-2 rows across upgrade/downgrade/re-upgrade; failure regression proves prior revision is not advanced for the tested failure case. |
| D3-29 | Tests cover URL, PDF, DOCX, CSV, JSON and manual metadata with synthetic/mocked inputs. |
| D3-30 | Tests cover duplicates, corrupt documents, unsupported content, invalid lifecycle, approval gating, failed activation rollback, single-active invariant and stale competing-candidate re-review. |
| D3-31 | Tests persist revision-aware provenance and reject analytical evidence as provenance for a hard official policy. |
| D3-32 | `python -m app.source_verify` / `make source-verify` demonstrates first activation, changed candidate, pattern drift, no silent update and approved replacement. |
| D3-33 | Full Day-1/Day-2 regression, Ruff, Mypy, frontend typecheck/build, migration checks and Compose smoke are required in CI on the exact handoff revision. |
| D3-34 | This report, D03 Founder UAT, exact tested Git revision and matching archive/checksum form the Day-3 handoff. |

## Acceptance evidence

Primary tests:

- `backend/tests/test_source_intelligence.py`
- `backend/tests/test_source_intelligence_migration.py`
- existing Day-1/Day-2 regression suite
- `python -m app.source_verify`
- GitHub Actions backend, frontend and Compose jobs

## Important boundaries

Day 3 does **not** claim:

- official NCF/NCERT/CBSE/Telangana content population;
- live AnythingLLM RAG/embedding/workspace integration;
- OCR;
- LangGraph generation;
- public Source CRUD APIs/auth;
- final React Source Admin UI;
- Day-4 work.

These remain assigned to their planned later days.

## Founder handoff

Use `docs/execution/D03-FOUNDER-UAT.md`.

Day 4 must remain locked until explicit Founder Day-3 signoff.
