# C00-09/10 — Residual register (candidate 3/3)

## P0 (source/exam/trust blockers)

| ID | Affected tasks | Evidence link | Workstream | Prereq | Acceptance proof |
| --- | --- | --- | --- | --- | --- |
| RES-PG-0021 | D13-31, D13-31A, D17-* migrations | `C00-MIGRATION-INVENTORY.md` | **C01** | Isolated PG | Live upgrade green without history rewrite |
| RES-MIG-DUP-0022 | held PR57+PR61 | duplicate `20261124_0022` ids | **C01** | Graph plan | Single authoritative head before merge |
| RES-SRC-012 | D4-* | CI 42783645367; issue #12 | **C02** | Curator bytes | ACTIVE SourceRevision |
| RES-SRC-016 | **D5-DS01**, PKG-1..5 | issue #16; `C00-SOURCE-EVIDENCE.md` | **C02** | Founder bytes | Five Telangana packages ACTIVE |
| RES-HOLD-031 | D11-01..36 | PR #31 @ d0f0745f | **C06** | C02 NTA | Independent task PASS or explicit open |
| RES-HOLD-057 | D15-01..36, D15-R3-* | PR #57 @ b69f97bf; comment 7133926987 | **C10** | **C12** | Safe merge + trusted runtime |
| RES-HOLD-061 | D17-01..36, D17-F* | PR #61 @ 87df6a54; CI 45535514058:FAILED | **C12/C13** | C01 PG | Exact-HEAD green + clean review |
| RES-D12-CORE | D12-CORE-01..06 | issue #35 | **C07** | D3 + six slots | Fail-closed source authority |

## P1 (deferred milestone / containment)

| ID | Tasks | Workstream |
| --- | --- | --- |
| RES-D12-ISSUE-44 | D12-ISSUE-44 | **C07** |
| RES-D12-ISSUE-45 | D12-ISSUE-45 | **C07** |
| RES-D13-STOP | F03-A→D13-12, F03-B/F04-A→D13-23, D13-31A | **C08** |
| RES-D14-R3 | D14-R3-01..06 | **C09** |
| RES-D15-R3 | D15-R3-01..06 (MS01–MS04) | **C10** |
| RES-D16-F | D16-F01..03 | **C11** |
| RES-D18-F | D18-F01..06 | **C14** |

## C15 vs Day19

**C15** = frozen integration acceptance umbrella only. **Day19 UAT** remains a separate locked gate (not conflated with C15 technical closure).

## C01 proposed diagnostics (planning — LOCKED)

1. Reproduce PG0021; capture Alembic error + DDL diff (**UNKNOWN** artifact today).
2. Duplicate `0022` rename/branch strategy — no execution.
3. Held `0023/0024` reconciliation after (2).
4. SQLite revision file checksum at `8b71aa03` (read-only).
5. Backup/restore checklist item for C15.

## Workstream row counts (ledger-derived)

| WS | Rows |
| ---: | ---: |
| C01 | 83 |
| C02 | 47 |
| C03 | 82 |
| C04 | 94 |
| C05 | 108 |
| C06 | 36 |
| C07 | 46 |
| C08 | 42 |
| C09 | 42 |
| C10 | 42 |
| C11 | 39 |
| C12 | 22 |
| C13 | 21 |
| C14 | 48 |
| C15 | 0 (umbrella only in planning) |

*714 total unique IDs; alias/DOD IDs are labeled in `original_authority`.*