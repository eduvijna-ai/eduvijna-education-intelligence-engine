# C00-09/10 — Residual register (candidate 2/3)

## P0 (source/exam/trust blockers)

| ID | Affected tasks | Evidence link | Workstream | Prereq | Acceptance proof |
| --- | --- | --- | --- | --- | --- |
| RES-PG-0021 | D13-31, D13-31A, D17-* migrations | `C00-MIGRATION-INVENTORY.md` | **C01** | Isolated PG | Live upgrade green without history rewrite |
| RES-MIG-DUP-0022 | held PR57+PR61 | duplicate `20261124_0022` ids | **C01** | Graph plan | Single authoritative head before merge |
| RES-SRC-012 | D4-* | CI 42783645367; issue #12 | **C02** | Curator bytes | ACTIVE SourceRevision |
| RES-HOLD-031 | D11-01..36 | PR #31 @ d0f0745f | **C06** | C02 NTA | Independent task PASS or explicit open |
| RES-HOLD-057 | D15-01..36, D15-R3-* | PR #57 @ b69f97bf | **C10** | **C12** | Safe merge + trusted runtime |
| RES-HOLD-061 | D17-01..36, D17-F* | PR #61 @ 87df6a54; CI 45535514058 | **C12/C13** | C01 PG | Exact-HEAD green + clean review |

## P1 (deferred milestone / containment)

| ID | Tasks | Workstream |
| --- | --- | --- |
| RES-D12-35 | D12-CORE-35, slots 1–6 | **C07** |
| RES-D13-STOP | F03-A→D13-12, F03-B/F04-A→D13-23, D13-31A | **C08** |
| RES-D14-R3 | D14-R3-01..06 → D14-30, D14-09, etc. | **C09** |
| RES-D16-F | D16-F01..03 | **C11** |
| RES-D18-F | D18-F01..06 | **C14** |

## Workstream assignment rules applied (per #64)

- **D4-*** → **C03** (national curriculum evidence), not C02.
- **D17-F01,F05,F06,F07** → **C12** (identity/auth).
- **D17-F02,F03,F04** → **C13** (REST/jobs/MCP).
- **C15** = frozen integration acceptance only; **Day19 UAT** remains separate locked gate (no circular dependency).

## C01 proposed tasks (planning — still LOCKED)

1. Reproduce PG0021 on empty + populated PostgreSQL; capture Alembic error + DDL diff.
2. Document integration strategy for duplicate `0022` (rename vs branch) — no execution.
3. Reconcile held `0023/0024` only after (2).
4. SQLite targeted migration smoke on `8b71aa03` (read-only checksum of revision files).
5. Backup/restore checklist item for C15.

## Amendment / residual row coverage

Ledger includes **D14-R3-01..06**, **D15-R3-01..06**, **D16-F01..03**, **D17-F01..07**, **D18-F01..06**, **F03-A/B**, **F04-A**, **D13-31A**, **D12-CORE-35** with parent task links and residual_finding_ids populated.