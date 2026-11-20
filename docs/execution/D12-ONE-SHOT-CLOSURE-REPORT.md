# D12-ONE-SHOT-CLOSURE-01 — consolidated engineering handback (Issue #44)

**Parent issue:** [#44](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/44)  
**PR:** [#34](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/34) (`feature/day12-jee-advanced-intelligence` → `develop`)  
**Frozen start SHA (authorized):** `890608887fdad1effa44b6112e399d662e7c83e0`  
**Candidate HEAD:** _(see PR comment `EDUVIJNA_CURSOR_COMPLETE` after push)_  
**Governance:** `founder_approval:false`; Day11 PR31 ON_HOLD; Day13 LOCKED; D12-36 **not** self-signed.

## Executive verdict (honest)

| Bucket | Count | Notes |
|--------|------:|-------|
| Engineering PARTIAL+ | 28 | Code + negative tests; not whole-task official PASS |
| SOURCE_PENDING | 6 | D12-02, D12-03, curator bytes, syllabus ACTIVE, reference blueprint pins |
| NOT_STARTED (process) | 1 | D12-36 independent review + Founder signoff |
| PASS (official reference) | **0** | No fabricated IIT/JAB approval |

Official **36/36 PASS** remains impossible without Founder-provisioned curator registry, original private PDF bytes, rights decisions, and live PG/AnythingLLM/UAT.

## M0 — 36-row ledger (post one-shot)

See updated `docs/execution/D12-SCOPE-MAP.md`. Summary: **0 PASS / 28 PARTIAL / 6 SOURCE_PENDING / 1 NOT_STARTED (D12-36 process)**.

## Source / identity inventory (no bytes, no secrets)

| Slot | Primary URL | Alternate | Staged SHA (builder) | Rights | Curator |
|------|-------------|-----------|----------------------|--------|---------|
| Brochure | `…/IBEnglish_2026.pdf` | `…/IBEnglish_2026_1.pdf` | null (tests mock only) | RIGHTS_REVIEW_PENDING | CURATOR_PENDING |
| Syllabus | `…/jee-advanced-2026-syllabus.pdf` | — | null | RIGHTS_REVIEW_PENDING | CURATOR_PENDING |
| Paper 1 | `…/p1_english.pdf` | — | null | RIGHTS_REVIEW_PENDING | CURATOR_PENDING |
| Paper 2 | `…/p2_english.pdf` | — | null | RIGHTS_REVIEW_PENDING | CURATOR_PENDING |
| Key P1 | `…/p1_solutions_final.pdf` | — | null | RIGHTS_REVIEW_PENDING | CURATOR_PENDING |
| Key P2 | `…/p2_solutions_final.pdf` | — | null | RIGHTS_REVIEW_PENDING | CURATOR_PENDING |

Live builder fetch to `jeeadv.ac.in` often **404/FETCH_BLOCKED**; brochure alternate tried in code when primary fails (mock-tested).

## Engineering deltas (Issue #44)

1. **Staging trust:** `no_autoflush` on protected-revision preflight; `year_2024` in conflict matrix; brochure ordered fallback URL; protected revision with **missing `storage_path`** still read-only preflight.
2. **New modules:** `syllabus_catalogue.py`, `historical_inventory.py`, `constraint_precedence.py`, `reasoning_profile.py`, `verification_orchestration.py` (D12-09…13, 16, 26–31 wiring).
3. **Tests:** `tests/test_day12_one_shot_closure.py` + expanded ingest adversarial vectors; `.eduvijna/pytest-targets.txt` updated.

## CI / local verification (builder)

| Command | Result |
|---------|--------|
| `ruff check app tests` | **PASS** |
| `mypy app` | **PASS** (308 source files) |
| `pytest tests/test_day12_*.py` | **PASS** (94 tests, 11 modules) |
| `pytest $(cat .eduvijna/pytest-targets.txt)` | **PASS** |
| `python -m app.day12_verify` | exit 0; `reference_2026_curator_approved:false` |
| `pytest tests/` full historical | **PASS** (exit 0, ~30m builder) |
| Docker Compose / live PostgreSQL | **NOT_RUN** |
| AnythingLLM live | **NOT_RUN** |
| Founder localhost UAT | **NOT_RUN** |

## Known gaps (non-delegable)

- Provision `jee_advanced_source_curators@v1` + active `AdminActor` curators.
- Private ingest of authentic 2026 six-slot PDFs + human approve/activate.
- Pin complete paper-specific `ExamBlueprintRule` rows from approved instructions.
- Day3 **ACTIVE** preflight SQLite fixture blocked by `ck_source_revision_active_slot` (ACTIVE path shares query with APPROVED; **NOT_PROVEN** in SQLite manual fixture only).
- D12-36 Chief Architect exact-HEAD review after Founder “Cursor completed”.

## Founder-local demo (reproducible)

```bash
cd backend && python -m app.day12_verify
```

Expects synthetic Math10/Algebra10, shortage vectors, `official_2027_approved:false`, `reference_2026_curator_approved:false`.

## Blocker assignment

| Blocker | Owner |
|---------|--------|
| Original PDF bytes + rights | Founder / IIT-JAB |
| Curator registry + activation | Founder |
| D12-36 acceptance | Chief AI Architect + Founder |
| Live PG replay proof | Founder infra (optional) |