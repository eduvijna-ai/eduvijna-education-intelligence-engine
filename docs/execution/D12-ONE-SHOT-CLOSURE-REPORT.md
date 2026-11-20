# D12 consolidated evidence report (Issues #44–#47)

**PR:** [#34](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/34)  
**Issue #47 start SHA:** `9a5ab9e0cd132fef226870ede6701b0e4b3bf555`  
**Issue #46 parent:** `a705e00f08f81ace53dcc874eb7fc3a448c769e0`  
**Governance:** `founder_approval:false`; D12-36 **NOT_STARTED**; no merge.

## Issue #47 production integration (PROD-47-01…04)

| Gate | Fix | Tests |
|------|-----|-------|
| PROD-47-01 | `persisted_question_loader.py` + by-id verification; unit identity; zero tolerance; record org scope | `test_day12_production_integration.py` |
| PROD-47-02 | `syllabus_graph.py` loads `CurriculumNode`, competency links, PCM coverage | `test_prod47_02_*` |
| PROD-47-03 | Gateway protocol chain, affirmative review, `production_orchestration.py`, cross-process pair | `test_prod47_03_*` |
| PROD-47-04 | Ruff/mypy/Day12/scoped targets; ledger unchanged | `test_prod47_04_*`, `test_ready04_*` |

## Ledger (mechanical, 36 rows)

**0 PASS / 32 PARTIAL / 3 SOURCE_PENDING / 1 NOT_STARTED** — verified by `test_f05_scope_map_sums_to_36_rows` / `scope_ledger.load_repo_scope_counts`.

## Issue #46 readiness gates (READY-01…04)

| Gate | Fix | Tests |
|------|-----|-------|
| READY-01 | Stored answers from `Question` options/`answer_json`/`rubric_json`; no caller `correct` | `test_day12_engineering_readiness.py` |
| READY-02 | `syllabus_graph.py` reviewed concept/LO/competency | `test_ready02_*` |
| READY-03 | `orchestration_chain.py` AUTHOR→SOLVER→REVIEW | `test_ready03_*` |
| READY-04 | Ruff UP037 fix; scope tally | `test_ready04_*` |

## Issue #45 closures (F01–F05)

| Finding | Fix | Tests |
|---------|-----|-------|
| **F01** Forged solver dict PASS | `independent_verification.py` + shared `independent_solver_proof.py`; legacy dict routes fail closed | `test_day12_acceptance_fix.py` (forged/stale/foreign/multiselect/numeric) |
| **F02** Caller OFFICIAL flag | `resolve_authoritative_constraint_layer(session,…)`; boolean helper non-authority | `test_f02_*` |
| **F03** Placeholder syllabus READY | `evaluate_slot_authority` + LO rows + page locator | `test_f03_*` |
| **F04** Stub orchestration | `FakeGenerationGateway` author→solver probe; question-bound cognitive | `test_f04_gateway_probe_executes_calls` |
| **F05** Brochure requested URL | `requested_url` from actual hop; scope tally | `test_f05_brochure_alternate_requested_url_persisted` |

## Builder verification (pre-push)

| Command | Result |
|---------|--------|
| `ruff check app tests` | PASS |
| `mypy app` | PASS (316 files) |
| `pytest tests/test_day12_*.py` | PASS |
| `pytest $(cat .eduvijna/pytest-targets.txt)` | PASS |
| `pytest tests/` full historical | BUILDER: see `/opt/cursor/artifacts/full-pytest-issue45.txt` when completed |
| Live PG / AnythingLLM / Compose / UAT | **NOT_RUN** |

## Nondelegable Founder actions

Authentic six-slot PDF bytes, rights, `jee_advanced_source_curators@v1`, blueprint pins, D12-36 signoff.