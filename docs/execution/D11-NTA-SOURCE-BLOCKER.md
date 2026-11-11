# D11 NTA 2027 original source — external evidence blocker

**Status:** NOT_VERIFIED (C1 workstream, 2026-11-11)

## What is blocked

Independent curator approval of **original** NTA JEE Main 2027:

- Information Bulletin 2027 (PDF bytes, SHA-256, page/section locators)
- Syllabus 2027 (PDF bytes, SHA-256, topic locators)

Candidate URLs are registered via `register_nta_2027_candidate_sources` but are **not** treated as production authority until:

1. Original PDF ingest through `SourceIntelligenceService` (not JSON/metadata stand-in)
2. Extraction, diff, validation, **Founder/curator approval** and activation
3. Pinned `SourceRevision` IDs on `ExamVersion` with `official_pattern_verified: true`
4. Immutable `ExamBlueprintRule` rows with `verified_official: true` matching bulletin counts/marks

## Production behaviour (correct)

- `OFFICIAL_PATTERN_REPLICA` + `TrustExecutionMode.PRODUCTION` → **FAIL** (`official_source_not_verified`)
- Synthetic 75/300 remains `synthetic_fixture_demonstration` only

## Manual handoff path

1. Download originals from `https://jeemain.nta.nic.in/documents/` (Founder/curator network)
2. Upload via approved Day-3 source UI or `SourceIntelligenceService.ingest_upload` with `application/pdf`
3. Complete review workflow; activate revisions; run curator pin to ExamVersion 2027
4. Re-run `source_authority.evaluate_official_pattern_authority` in **PRODUCTION** mode

**No Cursor/CI self-approval** of NTA authority.
