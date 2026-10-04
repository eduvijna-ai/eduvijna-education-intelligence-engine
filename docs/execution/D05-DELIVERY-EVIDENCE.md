# Day 5 engineering evidence and open source gate

## Delivery state

D5-01 through D5-34 remain approved on branch `feature/day5-telangana-curricula`. Day 5 stays **ACTIVE**; Day 6 stays **LOCKED**. Founder approval flags are unchanged.

Engineering adds official Telangana materialization (`telangana_official`, syllabus parsers, verification slice, extended manifest) on top of generic scoped curriculum contracts. The live official gate remains **fail-closed** until bounded slices materialize with complete catalogue evidence and unresolved blockers clear.

PR: https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/14

## Verified source status (local probe)

| Source | Retrieval | Notes |
|---|---|---|
| SCERT PS/BS English syllabi (PDF) | Often succeeds | Text extractable; hierarchy materialization depends on parser + exact wording guards |
| SCERT syllabus/textbook HTML indexes | Often fails | Connection reset / registry-only fallback |
| SCERT X Physical Science handbook (PDF) | Intermittent | Large PDF; pedagogy domain only |
| TGBIE `tgbienew.cgg.gov.in` annual plans (IA / IIA PDF) | Often succeeds | Text extractable |
| TGBIE scanned syllabus PDFs (IA) | Bytes fetchable | Image-only PDF; no extractable text without OCR |
| Legacy `tgbie.cgg.gov.in` | Blocked | F5 / stub HTML |

Official acceptance still requires: I–X textbook inventory bytes, Telugu correspondence, LO/academic-standard sources, applicability notices, and full catalogue denominators. Those remain named blockers in `day5_scope.json`.

## Task-to-evidence map (updated)

| Task | Evidence | State |
|---|---|---|
| D5-01 | `day5_scope.json`, `day5-verification-slice.json`, D05 spec | Named bounded chapters; blockers explicit |
| D5-02–D5-03 | Manifest + scope blockers | PARTIAL: authority/applicability notices not verified |
| D5-04–D5-08, D5-16–D5-25, D5-28–D5-29, D5-32–D5-34 | Scoped services/tests/verifier | ENGINEERING VERIFIED |
| D5-09–D5-15, D5-30–D5-31 | `telangana_official` + parsers | PARTIAL: bounded syllabus/annual-plan slices only when bytes + guards pass |
| D5-22 | `scoped_acceptance` + official report | Fail-closed until catalogues + slices reconcile |
| D5-26–D5-27 | CI + this document | Regression on candidate; Codex review open |

## Reproduce

From `backend` with Python 3.12 venv:

- `ruff check app tests`
- `mypy app`
- `pytest`
- `python -m app.domain_verify`
- `python -m app.source_verify`
- `python -m app.day4_verify`
- `python -m app.day5_verify`
- `python -m app.day5_verify --fetch-official` (expected nonzero while gate incomplete)
- `alembic upgrade head`; `alembic check`

From `frontend`: `npm run typecheck`; `npm run build`.

No verifier mutates the application database by default. Live bytes use private runtime storage only.
