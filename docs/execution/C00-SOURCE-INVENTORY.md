# C00-01 — Frozen baseline and source inventory

**Audit candidate:** 1/3  
**Governance HEAD (this branch):** `03fcd784b6a3940f04c1879a269a9987f87f677e`  
**Frozen application baseline (develop):** `8b71aa03bcff21f021f43ea430935edf14070f68`  
**Master register:** [Issue #64](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/64)  
**Draft PR:** [#65](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/65) → `develop`

## Verification (no drift)

| Check | Result |
| --- | --- |
| PR #65 state | open, draft, unmerged |
| PR head SHA | `03fcd784b6a3940f04c1879a269a9987f87f677e` (governance seed) |
| PR base SHA | `8b71aa03bcff21f021f43ea430935edf14070f68` |
| Branch ancestry | seed commit is direct child of frozen baseline merge commit |
| `AGENTS.md` | present; active workstream C00 audit-only |
| `.eduvijna/execution-state.yml` | consolidated_technical_closure C00 ACTIVE; Day19 locked; C01–C15 LOCKED |

## Original v1 / ARIV authority

| Artifact | Path / locator | Revision on disk | Retrieval scope | Status |
| --- | --- | --- | --- | --- |
| Engineering contract | `AGENTS.md` | branch HEAD | full file | AVAILABLE |
| Execution state | `.eduvijna/execution-state.yml` | branch HEAD | full file | AVAILABLE |
| Founder gates | `.eduvijna/founder-gates.yml` | branch HEAD | full file | AVAILABLE |
| Frozen 24-day v1 + ARIV master spec | **not present in public repository** | — | — | **MISSING_SPEC** — owner: Founder; request: attach immutable v1/ARIV register or private doc locator |
| Day 1–18 approved task specs | `docs/execution/D*.md` | mix of governance branch + `git show 8b71aa03:…` + held PR SHAs | per-day tables below | PARTIAL — see gaps |

## Day specification inventory (canonical task authority)

Denominators are **not** assumed to be 36 for every day.

| Day | Primary spec path(s) | Canonical row count in ledger | Notes |
| --- | --- | ---: | --- |
| 1 | `D01-FOUNDATION.md` (Definition of Done → `D1-DOD-01..25`) | 25 | No `D1-01..36` numbering in original spec |
| 2 | `D02-CANONICAL-DOMAIN-MODEL.md` (`D2-DOD-01..31`) | 31 | Checklist-based, not 36-task grid |
| 3 | `D03-COMPLETION-REPORT.md` + `D03-REWORK-CLOSURE.md` + `D03-FINAL-COMPATIBILITY-CLOSURE.md` | 46 | 36 core + `D3-R01..12` amendments |
| 4 | `D04-DELIVERY-EVIDENCE.md` / `D04-NCF-NCERT-CBSE.md` | 47 | `D4-01..47` per Issue #64 |
| 5 | `D05-DELIVERY-EVIDENCE.md` + `D05-DS01-TELANGANA-AUTHORITATIVE-SOURCES.md` | 35 | `D5-01..34` + `D5-DS01` |
| 6 | `D06-SCOPE-MAP.md` + `D06-DELIVERY-EVIDENCE.md` (D6-A*) | 44 | 36 + closure amendments |
| 7 | `D07-SCOPE-MAP.md` + `D07-PRODUCTION-IDENTITY-CLOSURE.md` | 46 | 36 + `D7-PIC-01..10` |
| 8 | `D08-SCOPE-MAP.md` / `D08-LANGGRAPH-ORCHESTRATION.md` | 36 | |
| 9 | `D09-SCOPE-MAP.md` | 36 | |
| 10 | `D10-SCOPE-MAP.md` / `D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md` | 36 | |
| 11 | `git show d0f0745f:docs/execution/D11-SCOPE-MAP.md` (PR #31 held) | 36 | Spec also references `D11-JEE-MAIN-EXAM-INTELLIGENCE.md` — **MISSING_SPEC on develop@8b71aa03** (exists on held branch only) |
| 12 | `D12-SCOPE-MAP.md` | 36 | |
| 13 | `D13-SCOPE-MAP.md` + closeout docs | 40 | 36 + stopped-workstream amendment IDs |
| 14 | `D14-SCOPE-MAP.md` | 42 | 36 + `R3-01..06` residual rows |
| 15 | `git show b69f97bf:docs/execution/D15-SCOPE-MAP.md` (PR #57 held) | 36 | Unmerged |
| 16 | `D16-SCOPE-MAP.md` | 39 | 36 + `D16-F01..03` |
| 17 | `git show 87df6a54:docs/execution/D17-SCOPE-MAP.md` (PR #61 held) | 43 | 36 + `D17-F01..07` |
| 18 | `D18-SCOPE-MAP.md` | 42 | 36 + `D18-F01..06` |

**Ledger total canonical IDs:** 696 rows (`C00-MASTER-TASK-EVIDENCE.csv`), validated unique.

## GitHub issue / PR anchors (Day 1–18)

| Day | Issue | Merged PR | Held PR | Frozen held HEAD (verified) |
| --- | ---: | ---: | ---: | --- |
| 1 | #2 (PR) | #2 | — | — |
| 7 | — | #23 (supersedes #22) | #22 audit history | — |
| 10 | #28 | #29 | — | — |
| 11 | #30 | — | #31 draft | `d0f0745f6573bba0cfa93fa8eb0674cdd3b689d2` |
| 12 | #33 | #34 | — | — |
| 13 | #52 | #53 | — | — |
| 14 | #54 | #55 | — | — |
| 15 | #56 | — | #57 draft | `b69f97bf9ee1cb08e16121f301dc20e5e5645f6f` |
| 16 | #58 | #59 | — | — |
| 17 | #60 | — | #61 draft | `87df6a54ea8ad1c06157f894b4a4c4a1bfa3bbc1` |
| 18 | #62 | #63 | — | — |

## MISSING_SPEC register (do not reconstruct)

| ID | Missing authority | Owner | Evidence request |
| --- | --- | --- | --- |
| MS-001 | Frozen original 24-day v1 + ARIV requirements document (bytes) | Founder | Private attach or SHA-labeled store |
| MS-002 | `D11-JEE-MAIN-EXAM-INTELLIGENCE.md` on merged develop | Founder/C06 | Use held PR #31 ref for planning; not merged baseline |
| MS-003 | Founder attachment archive for early Day 1–2 task numbering | Founder | If distinct from DoD checklists, supply locator |

## Test / CI scope for this audit

Full historical pytest, Compose, live PostgreSQL, AnythingLLM, and browser UAT: **NOT_RUN** (audit-only). Baseline code inspection uses static paths recorded in the ledger at `8b71aa03` unless noted **NOT_VERIFIED**.