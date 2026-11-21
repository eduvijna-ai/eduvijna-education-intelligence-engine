# D12 consolidated evidence report (Issues #44–#47)

**PR:** [#34](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/34)  
**Issue #51 closure start SHA:** `c4001d5a2a04e2d6e05e35dfca6b69ac644efa17`  
**Issue #51 start SHA:** `4725523e20de9aa8a13aa0c50edc77e5aad8afe5`  
**Issue #50 start SHA:** `6ec6de4b41ef4ccdaa050ae25cc3bd7367017044`  
**Issue #49 start SHA:** `ad895980120f0a8a5bf3ae4e157ff40592345da0`  
**Issue #48 start SHA:** `3c628f015734915c3fe4799b4abc2d91ce95c0ee`  
**Issue #47 parent:** `9a5ab9e0cd132fef226870ede6701b0e4b3bf555`  
**Governance:** `founder_approval:false`; D12-36 **NOT_STARTED**; no merge.

## Issue #51 E2E truth gate (F51-01…03)

| Gate | Fix | Tests |
|------|-----|-------|
| F51-01 | Independent arithmetic author; fatal claim extractor; no `bound_correct_key` echo | `test_day12_e2e_truth_gate.py` |
| F51-02 | `d12-f52-v1` authoritative replay; gateway IDs + reviewer verdict | `test_f51_02_*` |
| F51-03 | Scoped pytest + ledger unchanged | Builder + CI; full `pytest tests/` BUILDER_REPORTED_ONLY at push |

## Issue #50 independent reasoning + replay integrity (F50-01…04)

| Gate | Fix | Tests |
|------|-----|-------|
| F50-01 | Answer-blind SOLVER payload; `independent_arithmetic_solver`; reject `solver_match_persisted` echo | `test_day12_independent_replay_integrity.py` |
| F50-02 | `author_draft_binding.py`; mandatory author draft fingerprint vs persisted Question | `test_f50_02_*`, `bound_synthetic_control` |
| F50-03 | Day6 audit/solver ID drift on replay; `no_autoflush` preflight; issuance record `d12-f50-v1` | `test_f50_03_*`, P48 replay |

## Issue #49 snapshot + answer binding (F49-01…03)

| Gate | Fix | Tests |
|------|-----|-------|
| F49-01 | `issuance_snapshot.py` stores immutable per-question fingerprints/Day6 scope; `_match_existing_pair` re-verifies live Question rows before `REPLAYED` | `test_day12_snapshot_answer_binding.py`, updated `test_day12_issuance_atomicity.py` |
| F49-02 | `chain_question_binding.py` + `solver_match_persisted` fake scenario; `clean_pass` B vs stored A blocks issuance | `test_f49_02_*` |
| F49-03 | Scoped pytest + ledger unchanged | `.eduvijna/pytest-targets.txt` |

## Issue #48 issuance atomicity (P48-01…03)

| Gate | Fix | Tests |
|------|-----|-------|
| P48-01 | `preflight_two_paper_pair` before gateway; replay = 0 gateway calls | `test_day12_issuance_atomicity.py` |
| P48-02 | `pair_issuance_validation.py` both questions Day6/solver before issue | `test_p48_02_*` |
| P48-03 | Integrated API cross-process replay | `test_p48_03_*` |

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