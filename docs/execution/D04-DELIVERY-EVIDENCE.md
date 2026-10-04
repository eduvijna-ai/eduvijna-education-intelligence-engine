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
| D4-04 | `ensure_framework`; exact content revision/version | Genuine official NCF content verified in hosted CI a0184ed |
| D4-05 | `FrameworkStructureNode`: stage → curricular area → goal → competency | Typed queryable hierarchy, no chapter flattening; reviewed initial NCF/NCERT slice |
| D4-06 | Official NCERT draft PDF pp46/56/57 plus typed LO registry/link | Original wording separated; draft status explicit; old unavailable URL retained |
| D4-07 | Canonical Competency + typed structure leaf | Stable codes/IDs, framework version, exact revision and locator; initial reviewed scope |
| D4-08 | `LearningOutcomeCompetencyLink`; framework path and curriculum path queries | Explicit LO→competency evidence; stage/area/goal and grade/subject/concept traversal |
| D4-09 | inferred/partial/unresolved statuses; direct requires content/locator/evidence | Implemented/tested; no invented official mapping asserted |
| D4-10 | `ensure_pack` | Implemented/tested |
| D4-11 | `ensure_version`, 2026-27 fixture | Implemented/tested |
| D4-12 | IX–XII catalogue/roots; detailed IX math, X math, XII physics paths | Initial locked scope; shared XI–XII catalogue rows explicitly unresolved by grade |
| D4-13 | explicit medium node | Implemented/tested |
| D4-14 | `catalogue.py`, version catalogue snapshot + explicit-grade subject nodes | Entire official index inventory, stable identities; ambiguous shared scopes preserved |
| D4-15 | `official_demo.py`, `baseline.py`; Unit → Chapter → Topic normalization | Source headings retained; derived topic/concept labels explicit; exact checked page locators |
| D4-16 | official text separate from derived metadata | Implemented/tested |
| D4-17 | deterministic UUIDs + repeated-ingestion test | Implemented/tested |
| D4-18 | hierarchy validation and schema constraints | Missing parent, duplicate codes, cycle regressions; earlier same-version FK regression |
| D4-19 | `CurriculumAlignment` + evidence fields | Implemented/tested |
| D4-20 | alignment input/status contract | Implemented/tested |
| D4-21 | Persisted-node alignment coverage + complete index denominator | Expected, materialized, shared/unresolved and detailed-path counts reported separately |
| D4-22 | no unsupported prerequisite edges seeded | Intentionally empty; rich intelligence remains Day 10 |
| D4-23 | official Class X/XII SQP/MS index manifest | Registered; retrieval availability separately reported |
| D4-24 | Typed AssessmentPattern/Section/QuestionCategory + numeric-summary extractor | Marks/count arithmetic validated; actual Maths/Physics baseline SQP extraction checked in CI |
| D4-25 | Assessment source type and immutable snapshot applicability checks | Grade, subject, year, node/version and domain rejection regressions |
| D4-26 | assessment-source rejection in `upsert_nodes` | Implemented/tested |
| D4-27 | Exact revision columns on all new structures/links and provenance query | Active-only writes; superseded historical reads; registry/synthetic classification explicit |
| D4-28 | superseded source references, version supersession | Prior references preserved; source-change regression |
| D4-29 | unchanged re-fetch and repeat seed tests | Implemented/tested |
| D4-30 | changed fetch diff/review gate | Active content remains until explicit review |
| D4-31 | public metadata only; private source storage | No source documents committed/uploaded as CI evidence |
| D4-32 | synthetic bundle/status/provenance; official acceptance false | Implemented/tested |
| D4-33 | `curriculum_intelligence/service.py` + Day 3 boundary | Implemented |
| D4-34 | generic framework/pack/version service | No CBSE-specific public controllers/core logic |
| D4-35 | `curriculum_path`, hierarchy path, coverage, counts | Internal query regression |
| D4-36 | `provenance()` | Exact revision, locator, checksum and classification |
| D4-37 | Source lifecycle + exact-byte/page checks + framework structure regressions | Real NCF/NCERT page proof already passed hosted CI; synthetic transport tests stay labeled |
| D4-38 | hierarchy/version/idempotency tests | Implemented/tested |
| D4-39 | Alignment/LO link status, inference, direct-evidence and scope guards | Direct published draft LO link and partial derived concept mapping remain distinct |
| D4-40 | assessment separation/binding tests | Implemented/tested |
| D4-41 | changed-source retains active reference regression | Implemented/tested |
| D4-42 | SQLite runtime suite; PostgreSQL DDL compilation in domain suite | No live PostgreSQL server claimed |
| D4-43 | Day4 populated migration; Day3 rollback/identity regressions; Alembic round-trip/check | Exact final result on PR |
| D4-44 | full regression/lint/mypy/frontend build; CI Compose | Local checks pass; final-head CI required |
| D4-45 | `python -m app.day4_verify --fetch-official` | Genuine official-content path verified at a0184ed; new baseline changes require final-head rerun |
| D4-46 | JSON inventory, entity counts, alignment coverage, catalogue denominator, unresolved items | Exact revisions/checksums/pages; full-content ingestion is never implied by index coverage |
| D4-47 | this mapping + final PR evidence | Pending final review/CI/source-backed acceptance; Day5 stays locked |

## Official-content proof (second correction)

The first correction `bcb4ef4a3371301a1faa6ed493414463e2157f6b` passed all CI jobs, including complete Compose API/env/persistence restart checks, in run `37208206466`. Local tests on that tree: 130 passed. The hosted metadata-only report proved eight actual URL-ingested active revisions; the original MoE NCF URL returned HTTP 404, and the original NCERT learning-outcomes URL remained unavailable.

A replacement NCF publication is linked by official Rajya Sabha answer 177 (24 July 2024), page 2: `https://ncert.nic.in/pdf/NCFSE-2023-August_2023.pdf`. It is approximately 47 MB. The official-evidence CI job alone explicitly configures `SOURCE_MAX_BYTES=67108864` (64 MiB). Application and normal verification defaults remain 25 MiB. The bound is tested and documented; no unrestricted download path is added. The original unavailable URLs remain in the inventory.

`curriculum_intelligence/evidence.py` verifies the Day-3 stored byte checksum and page-scoped evidence anchors. `official_demo.py` builds a separate representative source-backed path only after all checks pass. Its NCERT Grade 9 outcome remains explicitly DRAFT, and concept alignment stays derived/partial. It never labels this draft final, or claims full CBSE coverage. Full public source documents are never saved in the report.

The historical synthetic fixture was also corrected: the older CBSE Learning Standards PDF calls the Class IX chapter Number System; Real Numbers is a Class X chapter. That older document refers to NCF 2005 and has no verified 2026-27 applicability. It is not used to prove the current-year official path.

The second correction adds a Day-4 schema-failure rollback/retry test and content-evidence regressions for exact pages, tampered checksums, missing/registry sources, idempotent reviewed paths and the bounded explicit size setting. Until a live CI report confirms `official_demonstration.verified`, D4-45 remains blocked. The representative IX–XII scope includes an IX detailed path and explicit incomplete coverage elsewhere; assessment availability is separate and detailed pattern data remains unresolved.


## Complete initial-scope engineering contracts

The final candidate adds typed, queryable framework structure and explicit outcome→competency links with publication/review/inference status, exact revisions and locator fields. Historical revisions remain queryable, but all new curriculum/structure/alignment/assessment writes require active revisions. Assessment evidence is restricted to assessment sources and declared grade/subject/year applicability; assessment sources cannot establish curriculum alignments or membership.

The source-backed official index catalogue covers every discovered subject entry and supplemental/introductory resource separately. The inspected page contains 212 PDF anchors and 205 subject entries (69 IX, 63 X, 73 shared XI–XII). Shared entries remain candidate grade scopes, not silently accepted for each grade. The runtime report records expected index entries, materialized explicit-grade entries, unmaterialized/shared entries and detailed syllabus paths. Catalogue-only subjects are not represented as fully ingested content. Placeholders such as error.pdf never become published SQP/MS evidence.

Initial detailed content covers IX Mathematics, X Mathematics and XII Physics. Source headings are separate from derived topic/concept labels. The linked Physics syllabus cover has inconsistent 2025-26/2026-27 text, so its path explicitly remains source-review-required even though the publication link is under the 2026-27 official index. No unsupported Physics competency mapping is invented.

Typed assessment evidence validates paper totals, section totals, question counts, categories and source locators. The source-backed baselines are Class X Mathematics Standard (041): 80 marks, 38 questions, five sections; and Class XII Physics (042): 70 marks, 33 questions, five sections. Numeric section summaries are extracted from actual source text, checked against reviewed facts and reconciled arithmetically. Missing or changed summaries remain review-required. Marking schemes carry their own exact active source revisions; neither paper nor scheme changes syllabus membership. Competency emphasis that is not explicitly extracted stays unresolved rather than being invented.

All limitations above are part of the requested explicit unresolved-coverage contract. They do not assert full ingestion of every curriculum PDF or promote draft/contradictory source material into final rules. The Founder retains review of those source judgments; Day 5 stays locked. Final-head full tests/CI and independent Codex review are still mandatory before merge.
