# Day 4 delivery evidence and Founder verification

Scope: D4-01–D4-47 only. The exact-head PR checks and independent Codex review are the merge gates. This document does not record Founder signoff or unlock Day 5.

## What is implemented

- Versioned NCF/CBSE framework, CurriculumPack and academic version with exact SourceRevision provenance.
- Typed stage → curricular area → goal → competency hierarchy and explicit LO→competency evidence links. Draft/final, review status and inference are queryable fields.
- Canonical grade → medium → subject → unit → chapter → topic → concept paths. Official labels/locators remain separate from normalized/derived labels.
- Complete official-index inventory, persistent explicit-grade subject catalogue and honest expected/materialized/shared/unmapped coverage denominators.
- Separate typed assessment sections, marks, categories and source locators. Both SQP and marking-scheme revisions are first-class immutable evidence bindings; a changed scheme creates new evidence rather than overwriting history.
- Day-3 lifecycle reuse, active-only writes, preserved historical reads, changed-source review gates, strict source-domain/year/grade/subject boundaries, and blocked official-source reporting.

Synthetic verification uses distinct synthetic identifiers, inactive framework/pack/outcome/competency fixtures and a draft curriculum version. It cannot populate the canonical active CBSE pack. Fetched content alone does not prove a mapping: reviewed byte-checksum/page anchors and all required aggregate constituents must pass.

## Actual hosted source evidence

CI run `37210627019` at `02d5236c2e9bb8ee03ce317c1b157f0d583fc9e4` produced metadata-only artifact `11306497395` (ZIP SHA-256 `1c25498e255723c05c6d482eafc9fcb2c23f4a72acc25c6a15517a50f2adf2e4`). Inspection established:

- Official NCF 2023 bytes and NCERT Grade 9 draft pages 46/56/57 verified; framework structure and LO evidence created.
- CBSE IX Mathematics, X Mathematics (source page 3), and XII Physics (source pages 12–13) detailed paths verified.
- 212 curriculum PDF resources; 205 subject-index entries: IX 69, X 63, shared XI–XII 73. 132 explicit-grade catalogue subjects materialized; shared entries remain review-required.
- Class X SQP index: 61 parsed subjects, 15 unresolved rows; Class XII index: 78 subjects, 14 unresolved rows. Placeholders are not claimed as published documents.
- Actual Mathematics Standard SQP/MS: 80 marks, 38 questions, five typed sections; actual Physics SQP/MS: 70 marks, 33 questions, five typed sections. Both patterns were extracted, reconciled and verified.
- 158 curriculum nodes, two derived concept alignments, one reviewed learning outcome, a four-level framework structure, and separate assessment evidence.

That run exposed a reporting weakness: the old top-level flag checked only the IX path and the detailed-path count was hardcoded. The final implementation replaces that with a fail-closed aggregate across framework/LO links, all grade catalogue scopes, both baseline syllabus paths, both typed assessment patterns and both SQP inventories. The path count is derived from successful paths. A missing constituent produces an incomplete report and nonzero official-verification exit; CI still uploads that diagnostic report.

## Explicit source-review items

These are visible data judgments, not silently accepted final rules:

- The original MoE NCF URL returns 404. Its authoritative replacement is the NCERT-hosted NCF 2023 PDF, linked by Rajya Sabha answer 177 (24 July 2024), page 2. The old URL remains in the blocked inventory.
- The original NCERT learning-outcomes URL remains unavailable. The reviewed Grade 9 publication used here is explicitly DRAFT; its wording is never promoted to final status.
- The official Physics syllabus cover contains both 2025-26 and 2026-27. The path retains a source-review warning. No unsupported Physics competency mapping is invented.
- Shared XI–XII subject entries are candidates until their PDFs establish grade scope. Catalogue-only subjects are not claimed as fully ingested content.
- Physics B/C response categories are unspecified by the inspected instructions. Unextracted competency emphasis stays unresolved.
- No unsupported prerequisite edges are seeded; richer prerequisite intelligence remains Day 10.

The older synthetic Learning Standards example refers to NCF 2005 and has no verified 2026-27 applicability. Its Class IX chapter is Number System, not the Class X Real Numbers chapter. It is not used as current-year source-backed proof.

## Reproduce verification

From the repository root with Docker available:

```
make env
make lint
make test
make day4-verify
SOURCE_MAX_BYTES=67108864 make day4-verify-official
```

The last command explicitly opts this invocation into a bounded 64 MiB limit for the approximately 47 MB official NCF PDF. Application defaults remain 25 MiB; no unrestricted fetch path is added. The official-evidence CI job makes the same explicit bounded choice. If a required official site is unavailable, the report names the missing constituent and exits nonzero; it does not substitute unofficial content.

For a virtual-environment workflow, from `backend` run `pytest`, `ruff check app tests`, `mypy app`, `python -m app.domain_verify`, `python -m app.source_verify`, and `python -m app.day4_verify`. Live evidence: `SOURCE_MAX_BYTES=67108864 python -m app.day4_verify --fetch-official`. From `frontend`, run `npm install`, `npm run typecheck` and `npm run build`.

Run Alembic on a disposable validation database: upgrade head → downgrade -1 → upgrade head → check. Head is now 0009. Issued 0008 is restored unchanged; 0009 supports installations with either previously issued 0008 schema shape, validates adoption, backfills valid marking-scheme references without changing evidence IDs/audit records, and refuses a lossy downgrade instead of deleting or merging evidence.

Default verification databases are isolated. Use `--app-db` only when intentionally integrating into a reviewed application database; conflicting historical source bindings fail closed rather than silently rebind.

## Acceptance mapping

The initial reviewed scope is IX Mathematics, X Mathematics and XII Physics plus the complete official subject-index inventory. This is not a claim of full content ingestion for every CBSE subject. Tests are synthetic unless explicitly identified as the hosted live-source evidence above.

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
| D4-43 | Day4 populated migration; Day3 rollback/identity regressions; Alembic round-trip/check | 0009 compatibility, populated upgrade/downgrade, failure rollback and exact final checks on PR |
| D4-44 | full regression/lint/mypy/frontend build; CI Compose | Local checks pass; final-head CI required |
| D4-45 | `python -m app.day4_verify --fetch-official` | Genuine official-content path verified at a0184ed; new baseline changes require final-head rerun |
| D4-46 | JSON inventory, entity counts, alignment coverage, catalogue denominator, unresolved items | Exact revisions/checksums/pages; full-content ingestion is never implied by index coverage |
| D4-47 | this mapping + final PR evidence | All47 mapped; exact-head CI, aggregate source gate and Codex closure required; Day5 stays locked |


## Final engineering gate

The final review-fix batch passed 237 backend tests locally, plus Ruff and mypy. Frontend typecheck/build, SQLite migration round trips, PostgreSQL DDL compilation and full Docker Compose API/env/persistence restart checks were also verified during the delivery loop. The final PR records the exact final-head regression count, CI run, aggregate source-evidence artifact and independent Codex result. No failing/incomplete gate may be merged. Founder review follows; Day 5 stays locked.
