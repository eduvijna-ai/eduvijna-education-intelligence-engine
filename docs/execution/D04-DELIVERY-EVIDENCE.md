# Day 4 engineering delivery evidence

Status: IN PROGRESS — source-backed acceptance and final CI/Codex review are gates, not implied by a green synthetic test.

Scope remains D4-01–D4-47. Day 5 is locked. No Founder approval is recorded here.

## Corrections on PR 13

- Official retrieval extracts staged revisions before diff/validation/approval/activation.
- Official mode retries registry-only revisions and checks previously fetched content for changes. Changed content is staged for explicit review while the old active reference remains intact.
- DNS, HTTP retrieval and extraction failures record exact official URL and reason. No unofficial substitute is used.
- The deterministic curriculum bundle and provenance report explicitly identify synthetic/registry-only evidence. Fetching a PDF alone does not verify its curriculum mapping.
- SQP/MS sources cannot establish syllabus membership. Grade/subject/version bindings are checked independently.
- Docker builds include the public metadata manifests needed by both acceptance tests and the Founder command.
- The inherited 0007 snapshot-identity repair preserves colliding historical revision rows, references and audit records.

## Reproducible commands

From `backend`, with the backend virtual environment activated:

```
pytest
ruff check app tests
mypy app
python -m app.domain_verify
python -m app.source_verify
python -m app.day4_verify
python -m app.day4_verify --fetch-official
alembic upgrade head
alembic downgrade -1
alembic upgrade head
alembic check
```

From `frontend`: `npm install`, `npm run typecheck`, `npm run build`.

Docker-backed commands remain `make test`, `make lint`, `make day4-verify`, and `make day4-verify-official`. CI checks the complete Compose startup, env propagation and persistence restart flow. The separate `day4-official-evidence` job records source retrieval JSON as a metadata-only artifact; it deliberately does not upload source documents or claim that retrieval proves official mapping acceptance.

## Evidence boundaries

Local baseline at original `993b91a` was 107 passing tests. The resumed correction run reached 122 passing tests before final additional regressions. Ruff, mypy, frontend typecheck/build and upgrade/downgrade/re-upgrade/`alembic check` were run; exact final-head results are recorded on the PR after publication.

The cloud shell could not resolve any of the eight initial official hosts/URLs. The new JSON report explicitly returned `official_fetch_with_registry_fallback`, exact blocked URLs/reasons, and `official_source_backed_acceptance: false`. A metadata checksum is never represented as the original PDF checksum. The hosted CI retrieval report must be inspected separately.

The NCERT Grade 9 Phase I Part 2 publication is explicitly DRAFT. Registering it does not promote draft standards into final CBSE membership. Official-source inventory now also includes the NCERT publication index required by the specification.

## Acceptance mapping

“Implemented/tested” below describes an engineering contract, not completed official curriculum ingestion. “Partial/blocked” is an outstanding requirement.

| ID | Implementation / evidence | Current boundary |
|---|---|---|
| D4-01 | `content/curricula/day4_official_sources.json`; manifest schema; source inventory | Runtime content checksums require successful fetch; registry checksums labeled metadata-only |
| D4-02 | `ensure_manifest_sources`; fresh-fetch lifecycle regression | Implemented/tested |
| D4-03 | blocked fetch/DNS regressions; `blocked_sources` report | Implemented/tested; exact official source remains blocked |
| D4-04 | `ensure_framework`; source binding and version fields | Structure tested; genuine framework content acceptance pending |
| D4-05 | Separate framework, competency and chapter entities | No framework flattening; complete official NCF structure remains partial |
| D4-06 | `LearningOutcomeSpec`, outcome registry | Synthetic wording is explicitly unverified; official NCERT ingestion/mapping remains partial |
| D4-07 | `upsert_competencies`; stable ID + framework/revision links | Contract implemented; representative registry only |
| D4-08 | outcome version links, explicit alignment, internal path query | Engineering path tested; stage/grade/subject official breadth partial |
| D4-09 | inferred/partial/unresolved statuses; direct requires content/locator/evidence | Implemented/tested; no invented official mapping asserted |
| D4-10 | `ensure_pack` | Implemented/tested |
| D4-11 | `ensure_version`, 2026-27 fixture | Implemented/tested |
| D4-12 | IX–XII grade roots in verification slice | Representative scope only |
| D4-13 | explicit medium node | Implemented/tested |
| D4-14 | representative subject nodes, source-specific IDs | Full source-backed catalogue remains partial |
| D4-15 | node hierarchy + source locator | Contract tested; official normalization evidence partial |
| D4-16 | official text separate from derived metadata | Implemented/tested |
| D4-17 | deterministic UUIDs + repeated-ingestion test | Implemented/tested |
| D4-18 | hierarchy validation and schema constraints | Missing parent, duplicate codes, cycle regressions; earlier same-version FK regression |
| D4-19 | `CurriculumAlignment` + evidence fields | Implemented/tested |
| D4-20 | alignment input/status contract | Implemented/tested |
| D4-21 | `coverage()` | Representative fixture denominator, not entire CBSE catalogue |
| D4-22 | no unsupported prerequisite edges seeded | Intentionally empty; rich intelligence remains Day 10 |
| D4-23 | official Class X/XII SQP/MS index manifest | Registered; retrieval availability separately reported |
| D4-24 | `AssessmentEvidence.evidence_json` | Structured contract; extracted sections/marks not yet demonstrated |
| D4-25 | version/type/year/grade checks | Wrong-grade regression; academic year enforced |
| D4-26 | assessment-source rejection in `upsert_nodes` | Implemented/tested |
| D4-27 | exact revision columns/provenance query | Exact binding tested; registry/synthetic classification explicit |
| D4-28 | superseded source references, version supersession | Prior references preserved; source-change regression |
| D4-29 | unchanged re-fetch and repeat seed tests | Implemented/tested |
| D4-30 | changed fetch diff/review gate | Active content remains until explicit review |
| D4-31 | public metadata only; private source storage | No source documents committed/uploaded as CI evidence |
| D4-32 | synthetic bundle/status/provenance; official acceptance false | Implemented/tested |
| D4-33 | `curriculum_intelligence/service.py` + Day 3 boundary | Implemented |
| D4-34 | generic framework/pack/version service | No CBSE-specific public controllers/core logic |
| D4-35 | `curriculum_path`, hierarchy path, coverage, counts | Internal query regression |
| D4-36 | `provenance()` | Exact revision, locator, checksum and classification |
| D4-37 | fresh fetched lifecycle, fixtures, blocked source tests | Real NCF/NCERT content run remains blocked locally |
| D4-38 | hierarchy/version/idempotency tests | Implemented/tested |
| D4-39 | status model + inferred/direct guard tests | Official direct alignment evidence remains partial |
| D4-40 | assessment separation/binding tests | Implemented/tested |
| D4-41 | changed-source retains active reference regression | Implemented/tested |
| D4-42 | SQLite runtime suite; PostgreSQL DDL compilation in domain suite | No live PostgreSQL server claimed |
| D4-43 | Day4 populated migration; Day3 rollback/identity regressions; Alembic round-trip/check | Exact final result on PR |
| D4-44 | full regression/lint/mypy/frontend build; CI Compose | Local checks pass; final-head CI required |
| D4-45 | `python -m app.day4_verify` | BLOCKED: synthetic path is not official source-backed acceptance |
| D4-46 | verification JSON inventory/counts/coverage/blocked items | Representative scope report; official completeness not claimed |
| D4-47 | this mapping + final PR evidence | Pending final review/CI/source-backed acceptance; Day5 stays locked |
