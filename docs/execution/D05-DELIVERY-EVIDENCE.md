# Day 5 engineering evidence and open source gate

## Delivery state

D5-01 through D5-34 are approved. This is a **partial engineering delivery, not Day 5 completion**. Day 5 stays ACTIVE; Day 6 stays LOCKED. Founder approval flags are unchanged. No release or merge is authorized by a green synthetic suite.

Base: `7f1f86fe9e24dee3a663f1e7702df0946c1138ba`. Draft PR: https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/14 . Source probe candidate: `98e19320dea722107e87bc959280eeb5bd4fedf1`; CI run 37220140777. Exact final-candidate CI and independent Codex findings belong in the PR timeline, not inferred from this earlier probe.

## Verified source failure

The bounded standard GitHub Actions run attempted six discovered official SCERT sources: syllabus index, English physical-science syllabus, English biological-science syllabus, draft textbook inventory, LO inventory and physical-science teacher handbook. All returned metadata-only fallback records; **zero official document bytes were verified**. The uploaded evidence contains only metadata, checksums and URLs. A checksum on a registry-only entry identifies its metadata, not a fetched PDF.

Evidence: https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/actions/runs/37220140777/artifacts/11309307769 . The Day 5 job correctly exited nonzero. The same run passed backend, frontend, Compose and Day 4 live official evidence.

The TGBIE portal previously returned F5 HTTP 403. It was not retried via CI or an unofficial mirror. Current First Year mathematics naming and applicability remain unverified. The historical Mathematics IA UAT has not been renamed or promoted to 2026–27. Competing 2025–26 DRAFT SCERT inventories must not be merged; bilingual Part 1/Part 2 do not imply different instructional media.

## New Intermediate portal discovery

The user supplied https://tgbienew.cgg.gov.in/home.do. Its readable official index separately lists 2025–26 IA/IB/IIA/IIB, 2026–27 revised First Year IA/IB, annual plans IA/IB/IIA/IIB, and revised subject-validation rules. A separate MEC model-paper label demonstrates why group applicability must remain distinct. The normal cloud browser returned F5 HTTP 403 on the new portal; no linked PDF bytes were verified. These index labels are preserved as discovery metadata in the scope file and do not unblock any detailed slice, medium or group claim.

## Task-to-evidence map

| Task | Implemented engineering evidence | Acceptance state |
|---|---|---|
| D5-01 | D05 spec, `day5_scope.json`, exact base and 34-task map | PARTIAL: named source chapters/version/medium frozen only after documents available |
| D5-02 | source manifest and separate unresolved publication/applicability fields | BLOCKED official authority notices/applicability |
| D5-03 | discovered SCERT URLs, domains, storage policy and named missing TGBIE source | PARTIAL: document inventories unavailable |
| D5-04 | reused SourceIntelligenceService; real synthetic registration/extract/diff/validate/approve/activate tests | ENGINEERING VERIFIED; live ingestion blocked |
| D5-05 | nonzero official verifier, registry-only diagnostics, required-slice blockers | ENGINEERING VERIFIED; source acquisition remains open |
| D5-06 | `ensure_pack/framework=None`, optional framework path, generic scoped two-pack demo | ENGINEERING VERIFIED; official packs not activated |
| D5-07 | explicit I–X versus First/Second Year in generic synthetic demo and queries | ENGINEERING VERIFIED; live names not populated |
| D5-08 | scoped catalogue identity, separate language/medium dimensions | ENGINEERING VERIFIED; actual media matrix blocked |
| D5-09 | exact-revision metadata catalogue storage and actual persisted row reconciliation | BLOCKED: actual SCERT inventory parser/materialization awaits bytes |
| D5-10 | independent year/paper/catalogue dimensions | BLOCKED: actual Intermediate inventory awaits bytes |
| D5-11 | exact version query; historical retrieval requires explicit flag, no current alias fallback | PARTIAL: official historical/current mathematics identity/successor records blocked |
| D5-12 | generic scoped Subject→Unit→Chapter→Topic→Concept chain; original wording checks | BLOCKED: official bounded hierarchy not materialized |
| D5-13 | source scope and separate media path contracts | BLOCKED: actual VIII PS/BS chapter UAT |
| D5-14 | two-year synthetic paths; unknown current/historical identity fails closed | BLOCKED: official mathematics UAT |
| D5-15 | independently sourced LO/competency writers, source scoped alignments | PARTIAL: no official Telangana mappings yet |
| D5-16 | exact reviewed cross-medium declarations; pair/text/locator rejection tests | ENGINEERING VERIFIED; official correspondence blocked |
| D5-17 | exact bytes, immutable snapshot checksum, approval fingerprint, grade/media/subject scope guards | ENGINEERING VERIFIED |
| D5-18 | domain-purpose gates across core and framework writers; assessment remains supporting only | ENGINEERING VERIFIED |
| D5-19 | immutable metadata/nodes, case/Unicode collisions, nested rollback, parent/pack/version tests | ENGINEERING VERIFIED |
| D5-20 | existing Day 3 change lifecycle preserved; scoped history read-only and safe replacement constraints | PARTIAL: live Telangana approved replacement demonstration blocked |
| D5-21 | `query_scoped_paths`, `query_catalogue`, provenance and historical flags | ENGINEERING VERIFIED |
| D5-22 | snapshot versus actual saved rows; duplicates/missing/tampering fail; dynamic required-slice gate | ENGINEERING VERIFIED; official denominators blocked |
| D5-23 | no schema changes; all issued migrations remain unchanged | Full legacy/fresh/populated regressions required on candidate |
| D5-24 | new Day 5 adversarial/synthetic tests; synthetic claims expressly separated | ENGINEERING VERIFIED |
| D5-25 | isolated `python -m app.day5_verify`; explicit `--fetch-official`, nonzero blocked gate | ENGINEERING VERIFIED |
| D5-26 | full backend/lint/types/frontend/verifiers/migration suites and CI | Exact final candidate results in PR; official Day 5 gate blocked |
| D5-27 | this map, reproduction commands, authentic artifact; Codex review pending | OPEN: no full completion/handoff claim |
| D5-28 | domain-purpose allowlists for syllabus/textbook/LO/standards/pedagogy/calendar/assessment | ENGINEERING VERIFIED |
| D5-29 | open medium labels, independent subject-language/role/part/bilingual dimensions | PARTIAL: every actual inventory row cannot be verified without snapshot |
| D5-30 | independent scoped outcome/standard sources and canonical entity reuse, no automatic NCERT equivalence | BLOCKED: selected official Telangana sources not ingested |
| D5-31 | course family and evidence-backed group applicability; unknown not universal | PARTIAL: official General/Vocational/groups materialization blocked |
| D5-32 | Unicode lossless original fields, separate normalized labels, corruption/collision gates and DB tests | ENGINEERING VERIFIED |
| D5-33 | private runtime storage, metadata-only explicit CI artifact paths; no bulk source files in Git | ENGINEERING VERIFIED |
| D5-34 | board-neutral core additions; generic second-pack synthetic proof with optional framework linkage | ENGINEERING VERIFIED; official second-pack acceptance blocked |

“Engineering verified” means the cited contract has deterministic code/tests, not that Day 5 is accepted. Some official source-specific parsers and reviewed manifests cannot be finalized before the documents are inspected. They are explicitly unfinished, rather than placeholders counted as success.

## Reproduce

From `backend`, using the project Python environment:

- `ruff check app tests`
- `mypy app`
- `pytest`
- `python -m app.domain_verify`
- `python -m app.source_verify`
- `python -m app.day4_verify`
- `python -m app.day5_verify`
- `python -m app.day5_verify --fetch-official` (expected nonzero while source gate remains blocked)
- `alembic upgrade head`; `alembic check`

From `frontend`: `npm run typecheck`; `npm run build`.

Compose equivalents: `make day5-verify` and `make day5-verify-official`. No verifier mutates the application database by default. Synthetic source bytes use a temporary private directory; live bytes use the existing ignored private source storage. PostgreSQL dialect compilation is not a live PostgreSQL test.

## Smallest source-unblocking step

Provide official SCERT syllabi and selected VIII Physical/Biological Science books, including the corresponding Telugu material and LO/academic standards, plus official Intermediate First/Second Year mathematics syllabus/version/group notices. Preserve the original issuing URL, academic edition/applicability and medium. Public Git must not receive these PDFs.

Use the existing private source lifecycle: `python -m app.source_cli --help`, register exact metadata, then `ingest-file SOURCE_ID PRIVATE_PATH --method pdf`. Review extraction, checksum, applicability, diff and scope before approval/activation. A manual metadata entry alone cannot unblock official acceptance. After inspection, replace unresolved scope selections with exact chapter/version/locator bindings, implement the matching inventory adapters, rerun official verification, review independently and return for Founder approval. Do not start Day 6.
