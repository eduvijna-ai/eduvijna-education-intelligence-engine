# C00-09/10 — Residual closure register and C01–C15 assignment

Priority: **P0** blocks learner/runtime gates; **P1** blocks technical acceptance before C15.

| Finding ID | Source | Affected tasks | Risk | Containment | Prerequisite | Workstream | Acceptance criterion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RES-PG-0021 | execution-state; C00-MIGRATION-INVENTORY | D13-31, D17-*, D18-* | P0 DB | synthetic/CAS only on SQLite | C01 root-cause on live PG | **C01** | Green upgrade on fresh + populated PG without history rewrite |
| RES-SRC-012 | issue #12; Day4 CI | D4-* | P0 evidence | official-source CI failed | C02 acquisition + curator | **C02** | Independent byte+SHA+ACTIVE revision |
| RES-SRC-016 | issue #16 | D5-DS01 | P1 Telangana | deferred | C02 packages | **C02** | Five packages approved |
| RES-SRC-032 | issue #32 | D11-* | P1 JEE Main | PR31 held | C02 NTA + C06 integration auth | **C06** | 2027 NTA curator-approved activation |
| RES-SRC-033-035 | issues #33,#35 | D12-* | P1 JEE Adv | live intake DISABLED | C02 six 2026 slots | **C07** | Version-specific rules with bytes |
| RES-HOLD-031 | PR #31 | D11-01..36 | P1 exam | ON_HOLD | C06 | **C06** | 36 rows independent PASS or explicit open |
| RES-HOLD-057 | PR #57 | D15-01..36 | P0 learner | runtime DISABLED | C12 then C10 | **C10** | Safe merge + trusted runtime evidence |
| RES-HOLD-061 | PR #61 | D17-01..36 | P0 API/auth | credentials DISABLED | C01 PG + C12/C13 | **C12/C13** | Failed CI257 resolved; manual review clean |
| RES-D13-STOP | D13 closeout | F03-A/B, F04-A, D13-31A | P1 replay | stopped workstreams | C08 | **C08** | Runtime spoof/unreadable adversarial cases |
| RES-R3 | D14 scope | R3-01..06 | P1 issuance | academic validation DISABLED | C09 | **C09** | Lift containment with evidence |
| RES-D16-F | PR #59 reviews | D16-F01..03 | P1 remediation | runtime DISABLED | C11 after C10 | **C11** | Nested trust + fingerprint proofs |
| RES-D17-F | PR #61 | D17-F01..07 | P0 security | Day17 ON_HOLD | C12/C13 | **C12/C13** | Exact-HEAD green targeted CI |
| RES-D18-F | PR #63 | D18-F01..06 | P1 UI | demo/synthetic surfaces | C14 after C13 | **C14** | Authenticated end-to-end artifacts |
| RES-UAT-ALL | Days 1–18 YAML | all Dxx-36 rows | P1 release | DEFERRED | C15 | **C15** | Full historical + Compose + Founder UAT |

## Dependency order (per Issue #64)

`C01/C02` → `C03/C04` → `C05` → `C06–C09` (exam packs) → **`C12` before real learner access** → `C10` → `C11` → `C13` → `C14` → `C15`.

## C01 first detailed proposal (planning only — not authorized execution)

| Proposed C01 task | Evidence to collect | Exit criteria |
| --- | --- | --- |
| PG0021 reproduction | Isolated PostgreSQL 15+; alembic upgrade from empty and from populated snapshot | Documented failure signature + DDL diff vs SQLite |
| Held migration graph reconciliation | Compare 0022–0024 on PR61 with any Day15 migrations | Single proposed integration branch plan without merge |
| Day1–3 config/health/tenant regression | Targeted tests on `8b71aa03` | CI or local log attached; no gate weakening |
| Backup/restore probe | pg_dump/restore after successful upgrade | Checklist for C15 |

**Owner:** Founder must authorize C01 implementation separately; C01 remains LOCKED in execution-state.