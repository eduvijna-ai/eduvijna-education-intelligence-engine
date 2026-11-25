# C00-12 — Audit report (candidate 2/3)

**Generator:** `python3 docs/execution/c00_build_ledger.py` then `c00_validate_ledger.py` at branch HEAD (see governance `candidate_2_sha` after push).

## Traceability repair summary (C00-F01..F05)

| Finding | Response |
| --- | --- |
| F01 Critical | Requirements from approved specs/issues; scope maps = implementation evidence only; D3 **34** core + 12 rework; D11 spec @ held SHA; D7-PIC titles from closure doc |
| F02 High | Historical vs technical columns split; no held PASS in `technical_acceptance_state`; mandatory fields populated |
| F03 High | Duplicate Alembic `20261124_0022` documented; granular source register |
| F04 High | Per-task workstreams; D14/D15 R3 disambiguation; P0 blockers listed |
| F05 High | Semantic validator + adversarial self-test hook |

## CI evidence (separate from ledger semantics)

| Run | Result |
| --- | --- |
| GitHub Actions **45542731473** (CI #267) | SUCCESS backend + frontend |
| Compose | SKIPPED |
| Audit ledger validator | `VALIDATION_OK` (local) |

## Counts (from validated ledger — not final Founder denominator)

| Metric | Value |
| --- | --- |
| Rows / unique IDs | **695** |
| `technical_acceptance_state` | NOT_VERIFIED 422; PARTIAL 200; SOURCE_PENDING 48; FOUNDER_REVIEW 25; **PASS 0** |
| `engineering_acceptance_state` | HISTORICAL_SCOPE_PARTIAL 254; HISTORICAL_ACCEPTED 361; … |
| Amendment/residual rows | D14-R3×6, D15-R3×6, D16-F×3, D17-F×7, D18-F×6, F03/F04/D13-31A, D12-CORE-35 |

### Per-day row counts

| Day | Rows | Notes |
| ---: | ---: | --- |
| 3 | 46 | 34 authoritative + 12 rework |
| 4 | 47 | D4-01..47 |
| 7 | 46 | 36 + D7-PIC-01..10 |
| 11 | 36 | held spec authority |
| 15 | 42 | 36 + D15-R3×6 |

## External checklist

- [ ] MS-001 external v1/ARIV bytes reconciliation
- [ ] Independent exact-HEAD review of candidate 2
- [ ] Founder “Cursor completed” for candidate 2/3
- [ ] C01 still **LOCKED**

Day19 and C01–C15 implementation remain **LOCKED**. PR **#65** stays **Draft**.