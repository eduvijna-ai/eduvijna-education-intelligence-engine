# C00-01 — Frozen baseline and source inventory (candidate 2/3)

| Item | Value |
| --- | --- |
| Frozen develop baseline | `8b71aa03bcff21f021f43ea430935edf14070f68` |
| Governance seed | `03fcd784b6a3940f04c1879a269a9987f87f677e` |
| Draft PR | [#65](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/65) |
| C00 candidate CI | [#267](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/actions/runs/45542731473) SUCCESS backend+frontend; Compose skipped |

## Ledger denominator stance

Candidate 2 ledger row count **695** is a **reproducible extraction** at immutable refs, **not** a claim of final Founder denominator. Rows include locally assigned Day1/2 DoD ids, amendments, and issue-linked scope rows where heading specs are absent on develop.

## Authoritative spec inventory

| Day | Primary authority (requirements text) | Supplemental evidence maps | Row count |
| ---: | --- | --- | ---: |
| 1 | `D01-FOUNDATION.md` DoD (`D1-DOD-*` local ids) | `D01-*` execution reports | 25 |
| 2 | `D02-CANONICAL-DOMAIN-MODEL.md` DoD | — | 31 |
| 3 | **`D03-SOURCE-INTELLIGENCE.md` D3-01..34** + rework D3-R01..12 | completion report = evidence only | 46 |
| 4 | `D04-NCF-NCERT-CBSE.md` checklist D4-01..47 | delivery evidence | 47 |
| 5 | `D05-TELANGANA-CURRICULA.md` + `D05-DS01` | delivery evidence | 35 |
| 6–10 | `D06`–`D10` approved tasklist markdown | `Dxx-SCOPE-MAP.md` implementation only | 36 each (+D7 PIC 10) |
| 11 | **`git show d0f0745f:docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md`** + issue #30 | held scope map | 36 |
| 12 | Issue **#33** tasklist; **#35** CORE; closeout **#44/#45** | `D12-SCOPE-MAP.md` | 37 |
| 13 | Issue **#52** | scope + closeout | 40 |
| 14 | Issue **#54** | scope + `D14-R3-*` | 42 |
| 15 | Issue **#56**; held scope `b69f97bf` | `D15-R3-*` | 42 |
| 16 | Issue **#58** | scope + `D16-F*` | 39 |
| 17 | Issue **#60**; held scope `87df6a54` | `D17-F*` | 43 |
| 18 | Issue **#62** | scope + `D18-F*` | 42 |

## MISSING_SPEC / external authority

| ID | Status | Notes |
| --- | --- | --- |
| MS-001 | **EXTERNAL_PENDING** | Original v1/ARIV attachment bytes not in repo. Founder/Chief Architect planning transcripts may exist **outside** Cursor context; reconcile separately. Do not copy private attachments. |
| MS-002 | **RESOLVED** | D11 authority readable at `git show d0f0745f:docs/execution/D11-JEE-MAIN-EXAM-INTELLIGENCE.md`; not MISSING on held ref. |
| MS-003 | CONDITIONAL | Early Day1/2 attachments only if distinct from committed DoD specs — none evidenced beyond `D01-FOUNDATION.md` / `D02-CANONICAL-DOMAIN-MODEL.md`. |

## Held PR verification (read-only)

| PR | HEAD SHA | Drift |
| ---: | --- | --- |
| 31 | `d0f0745f6573bba0cfa93fa8eb0674cdd3b689d2` | none |
| 57 | `b69f97bf9ee1cb08e16121f301dc20e5e5645f6f` | none |
| 61 | `87df6a54ea8ad1c06157f894b4a4c4a1bfa3bbc1` | none |

## Runtime testing (this workstream)

Full pytest, Compose, live PG, AnythingLLM, browser UAT: **NOT_RUN** (audit-only). C00 CI green does **not** prove CSV semantics.