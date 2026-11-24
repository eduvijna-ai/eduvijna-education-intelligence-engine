# Day 13 — Founder localhost UAT runbook (Round 1/3)

**Purpose:** Manual scenarios the Founder can run locally to observe **synthetic / reference-only** Day13 behavior.  
**This runbook does not claim UAT has been executed.** No Day13-specific public REST routes or frontend pages exist at SHA `dee224b662f7185eb19464eab74093979bec0448`.

## Environment prerequisites

| Step | Command / config | Notes |
|---|---|---|
| Python | 3.12, `cd backend && pip install -e '.[dev]'` | Same as CI |
| Database | `export DATABASE_URL=sqlite:///./eduvijna_local.db` (default dev) | PostgreSQL optional; migrations 0019–0021 PG risk per release-gates doc |
| Migrations | `python -m alembic -c alembic.ini upgrade head` | Includes Day13 replay table |
| API (optional) | `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` | Only `/health`, `/ready`, `/api/v1/*` system routes — **no CUET/CLAT practice HTTP API** |
| Frontend | `cd frontend && npm install && npm run dev` | Generic shell; **no Day13 UI** |

## Scenario matrix

| # | Scenario | How to run (localhost) | Expected (synthetic) | Official / NOT_READY |
|---|---|---|---|---|
| UAT-01 | CUET Math **10** questions | `cd backend && python -m app.day13_verify --json` → inspect `cuet_math_10` / practice block | **SYNTHETIC** count=10 demo | Official 10 from NTA-approved bank: **NOT_READY** (`SOURCE_PENDING`) |
| UAT-02 | CUET Math **50** full test | Same verifier → `cuet_single_test_50` or pytest: `tests/test_day13_f01_f02_repair.py` | Synthetic 50 arithmetic | Official 50: **NOT_READY** |
| UAT-03 | Wrong CUET **year** (2027) | `python -c` / pytest `test_day13_f01_f02_repair.py` (2027 requests) | Typed fail-closed / `NOT_READY` | Confirms isolation — not official verification |
| UAT-04 | Wrong **medium** | pytest `test_day13_f01_f02_repair.py` (`urdu` medium) | Typed non-PASS | Needs source-backed medium matrix (D13-10) |
| UAT-05 | CLAT **120** reference paper | `day13_verify` → `clat_paper_120` plan | **Reference-only** synthetic 120 + ranges | Official Consortium replica: **NOT_READY** |
| UAT-06 | CLAT **five section ranges** | `day13_verify` section counts vs `CLAT_SECTION_RANGES` | Approximate range demo | Exact official quotas: **not claimed** |
| UAT-07 | **Original passage** examples (EN/Legal/Logical/QT) | `day13_verify` → `clat_original_passage_examples` or `build_validated_clat_original_passage_examples()` in Python shell | Short **demo** originals from `copyright_passages.py` | F03-B production passage path: **STOPPED** |
| UAT-08 | **Current affairs** citation preflight | `day13_verify` F04-A block; harness token `F04A_HARNESS_TOKEN` in `clat_evidence_contracts.py` | Fail-closed / synthetic fixture receipts | Live news RAG + rights: **SOURCE_PENDING** / F04-A **STOP** |
| UAT-09 | **Tenant rejection** (foreign org) | pytest `test_day13_f03a_iter3.py` / `test_day13_d31a_durable_replay.py::test_foreign_tenant_no_replay` | `NOT_READY` / no cross-tenant replay | Production auth: not in scope |
| UAT-10 | **Stale replay** / idempotency | pytest `test_day13_d31a_durable_replay.py` (corrupt checksum, concurrent publish) | Typed `CORRUPT` / single winner | D13-31 **issuance** replay: **STOP** at D13-31A |
| UAT-11 | **Source authority** fail-closed | `build_source_registry_snapshot()` or `day13_verify` governance flags | `cuet_reference_curator_approved: false`, `clat_official_curator_approved: false` | Stays false until curator bytes |
| UAT-12 | Persisted CUET pool (harness) | pytest `test_day13_f03a_persisted.py` with `trusted_persisted_context` + `harness_authorized` | 50 validated **synthetic** math items | **Test harness only** — F03-A **STOP** |
| UAT-13 | Durable replay envelope | pytest `tests/test_day13_d31a_durable_replay.py` | SQL idempotency **without** question text in payload | Not Founder GUI; engineer pytest |

## Suggested Founder session (≈30 minutes, engineering-assisted)

1. Run `python -m app.day13_verify --json | jq` and review `trust_mode`, `source_pending`, and synthetic flags on each block.
2. Confirm **no** HTTP endpoint exposes full papers without going through test harness (inspect `app/api/router.py` — system routes only).
3. Optional: run `pytest tests/test_day13_core.py tests/test_day13_scoring.py -q` for quick green/red.
4. Record observations in a Founder UAT note for **R2** (not filed in R1).

## Explicit non-goals for localhost UAT

- No official NTA/Consortium PDF ingestion (Day12 #35 CLI disabled).
- No AnythingLLM live calls in default dev env.
- No claim that synthetic arithmetic equals CUET difficulty.
- No `founder_approval` toggle — Founder merges/signoff remain **R3**.

## Related docs

- [D13-CLOSEOUT-EVIDENCE.md](./D13-CLOSEOUT-EVIDENCE.md) — per-task ledger  
- [D13-CLOSEOUT-RELEASE-GATES.md](./D13-CLOSEOUT-RELEASE-GATES.md) — blockers and CI table  
- [D13-SCOPE-MAP.md](./D13-SCOPE-MAP.md) — engineering scope map