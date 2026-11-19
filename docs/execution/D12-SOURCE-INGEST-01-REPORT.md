# D12-SOURCE-INGEST-01 — Redacted six-slot acquisition report

**Issue #39** | **PR #34** | **Governance:** `reference_evidence_ready:false`, curator approval **not performed**, no PDF bytes in Git.

## SRC-01 — Direct URL manifest

Six slots map to official `jeeadv.ac.in/documents/` PDF URLs (discovery only until staging records checksums). See `export_src01_manifest()` and `OFFICIAL_DISCOVERY_URLS` in `backend/app/jee_advanced/constants.py`.

| Slot | Direct PDF URL | Rights |
|------|----------------|--------|
| `jee_advanced.2026.brochure` | https://jeeadv.ac.in/documents/IBEnglish_2026.pdf | RIGHTS_REVIEW_PENDING |
| `jee_advanced.2026.syllabus` | https://jeeadv.ac.in/documents/jee-advanced-2026-syllabus.pdf | RIGHTS_REVIEW_PENDING |
| `jee_advanced.2026.paper_1` | https://jeeadv.ac.in/documents/p1_english.pdf | RIGHTS_REVIEW_PENDING |
| `jee_advanced.2026.paper_2` | https://jeeadv.ac.in/documents/p2_english.pdf | RIGHTS_REVIEW_PENDING |
| `jee_advanced.2026.key_paper_1` | https://jeeadv.ac.in/documents/p1_solutions_final.pdf | RIGHTS_REVIEW_PENDING |
| `jee_advanced.2026.key_paper_2` | https://jeeadv.ac.in/documents/p2_solutions_final.pdf | RIGHTS_REVIEW_PENDING |

## SRC-02 / SRC-03 — Private staging (builder host, 19 Nov 2026)

Isolated fetch via `SourceUrlFetcher` + staging into `LocalSourceStorage` (gitignored). **No `approve_revision` / `activate_revision`.**

| Slot | Lifecycle | SHA-256 (actual bytes) | Size | Notes |
|------|-----------|------------------------|------|-------|
| brochure | **FETCH_BLOCKED** | — | — | HTTP 404 at direct URL; use manual PDF upload fallback |
| syllabus | STAGED (live) | `6dbc2abd1ab37e8f333dcc69020fcc8650de35b8f077acc7c8567d23a5373141` | 165910 | `%PDF` verified |
| paper_1 | STAGED (live) | `5864d8e10378892af0f833434bb8ba11b1839eabd75528937e7b10cc81daa95e` | 3245288 | `%PDF` verified |
| paper_2 | STAGED (live) | `5abc021da435c2f6357b376ab55a466ff25655d51bc4beccc5ed438b7b07c58e` | 2679043 | `%PDF` verified |
| key_paper_1 | STAGED (live) | `de728ea018819d23244abe358f955cb14ad1e698c4a20c7524d3c81e0ce1e2ca` | 2360177 | `%PDF` verified |
| key_paper_2 | STAGED (live) | `1cbf4be256594129810ba247681a4b7a96df7344c428a8194c77684d98094e38` | 2519342 | `%PDF` verified |

Local private staging entrypoint: `scripts/ingestion/jee_advanced_2026_private_stage.py` (writes under `backend/data/private/jee_advanced_2026_staging/`, excluded from Git).

## SRC-04 — Curator / rights handback (still pending)

1. Confirm `rights_reserved_review_required` for each staged document.
2. Provision real `jee_advanced_source_curators@v1` AdminActor entries (Founder action).
3. Human review of byte identity, paper/year/language, page locators, and blueprint completeness.
4. Only then: Day3 `approve_revision` + `activate_revision` on each slot.
5. `reference_evidence_ready` remains **false** until curator + blueprint gates pass; **2027 NOT_VERIFIED**.

## SRC-05 — Scope map

Unchanged unless separately evidenced: **0 PASS / 21 PARTIAL / 2 SOURCE_PENDING / 13 NOT_STARTED**.