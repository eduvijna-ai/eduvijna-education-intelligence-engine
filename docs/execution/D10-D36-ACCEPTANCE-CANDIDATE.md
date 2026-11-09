# Day 10 — D10-36 acceptance candidate report

**Frozen HEAD:** `dc482a0b8faabed4e9f36d0a12b40ea6f5ff200d`  
**Branch:** `feature/day10-prerequisites-root-cause-diagnostics` (Draft PR #29)  
**Verdict:** **Acceptance-candidate technical regression GREEN** @ migration fix; **D10-12/19/22/28/29/32/33 remain PARTIAL** per §3; **D10-36** awaits Chief Architect + Founder disposition (not self-approved).

## 1. Migration regression root cause and fix

### Reproduction (pre-fix @ `8f16350`)

`alembic check` after `upgrade head` on ephemeral SQLite:

```
ERROR: New upgrade operations detected: add_index on
  ix_curator_durable_approval_records_{decision_jti,admin_actor_id}
  ix_curator_operator_credentials_{organization_id,institution_id,teacher_id,curriculum_version_id,board_code}
```

**Cause (a):** SQLAlchemy models in `app/models/curator_auth.py` declare `index=True` on columns added in migrations `20261102_0015` / `20261103_0016`, but those migrations did not create matching indexes. **Not** env leakage or `stamp head`; genuine schema drift.

**Fix:** Successor migration `migrations/versions/20261109_0018_curator_model_index_parity.py` (revises `20261103_0017`).

**Re-run:** All 12 previously failing tests green locally with `PATH=$PWD/.venv/bin:$PATH` (Day3 rework/identity only failed in full suite when check failed at head).

## 2. Commands and evidence (final checkpoint)

| Command | Result |
|---------|--------|
| `ruff check app tests` | **PASS** |
| `mypy app` (274 files) | **PASS** |
| `pytest tests/test_day10_*` | **219 passed**, 0 failed (~43s) |
| `pytest tests/` full historical | **2058 passed**, 0 failed, exit **0** (~10m35s); log: `/opt/cursor/artifacts/d10-36-full-pytest-final.log` |
| Root-cause record | `/opt/cursor/artifacts/d10-36-migration-regression-root-cause.md` |
| `pytest tests/test_day10_r14_trust.py` | PASS (SQLite upgrade head + PG DDL compile) |
| `python -m app.day8_verify` / `day9_verify` / `day10_verify --json` | PASS @ final HEAD after push |
| Alembic head | **`20261109_0018`** |
| Frontend `npm run typecheck` / `build` | *(after `npm install`)* |
| Compose smoke | **NOT RUN** (Draft PR; CI skipped) |
| Live PostgreSQL | **NOT RUN** (DDL compile only) |
| Founder localhost/Docker UAT | **DEFERRED** — not passed |

## 3. PARTIAL task reconciliation (@ frozen requirements)

Criteria source: `docs/execution/D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md`.

### D10-12 — Misconception → concept mapping

| Criterion | Code path | Test(s) | Outcome | Status |
|-----------|-----------|---------|---------|--------|
| Versioned mapping with source lineage | `mapping_registry.py`, `mapping_claim_authority.py`, `mapping_evidence.py` | `test_day10_r17_trust.py`, `test_day10_r23_trust.py`, `test_day10_r27_trust.py`, `test_day10_r11_trust.py` (sourced production positive) | Signed overlay + revision binding enforced; synthetic veto in production | **PARTIAL** — no exhaustive catalogue/registry matrix for all misconception codes |

### D10-19 — LO/competency consistency

| Criterion | Code path | Test(s) | Outcome | Status |
|-----------|-----------|---------|---------|--------|
| Fail-closed Day6 binding in production RC | `root_cause_intelligence/day6_binding_verify.py` | `test_day10_r17_trust.py`, `test_day10_r19_trust.py` | LO/grade/medium mismatch → non-PASS | **PARTIAL** — not full cross-product matrix per spec table |

### D10-22 — Day-8/9 integration + HITL

| Criterion | Code path | Test(s) | Outcome | Status |
|-----------|-----------|---------|---------|--------|
| Compiled orchestration + root-cause enrich | `orchestration/nodes/root_cause.py`, `OrchestrationService` | `test_day10_r21_trust.py`, `test_day10_r12_trust.py`, `test_day10_r14_trust.py` | Production PASS with hypotheses in scoped fixtures; replay idempotency partial | **PARTIAL** — no full HITL interrupt/resume/restart matrix |

### D10-28 — Generic mandatory target policy

| Criterion | Code path | Test(s) | Outcome | Status |
|-----------|-----------|---------|---------|--------|
| Board mandatory merge, conflicts, auth | `mandatory_policy_resolver.py`, `target_policy_registry.py` | `test_day10_r18_trust.py`, `test_day10_r32–r35_trust.py` | Apply40 enforce, conflicts typed, durable discovery | **PARTIAL** — board→institution→teacher precedence not fully evidenced in one matrix |

### D10-29 — Integer target reconciliation

| Criterion | Code path | Test(s) | Outcome | Status |
|-----------|-----------|---------|---------|--------|
| Largest-remainder, fractional competency | `evaluator.py` `reconcile_exact_counts` | `test_day10_r9_trust.py`, `test_day10_r10_trust.py`, `test_day10_r12_trust.py` | 33/33/34, 50/50 fractional PASS | **PARTIAL** — institution/board mandatory precedence incomplete |

### D10-32 — Adversarial fixtures

| Criterion | Code path | Test(s) | Outcome | Status |
|-----------|-----------|---------|---------|--------|
| Tenant, forged evidence, cycles | `graph_verify.py`, `trust_verify.py`, `test_day10_adversarial.py`, `test_day10_r6/r8/r11/r33/r35_trust.py` | Broad negative coverage | **PARTIAL** — not single consolidated adversarial catalogue per D10-31/32 list |

### D10-33 — Batch/replay/portability

| Criterion | Code path | Test(s) | Outcome | Status |
|-----------|-----------|---------|---------|--------|
| SQLite migrate + PG DDL | `test_day10_r14_trust.py` | upgrade head @ `20261109_0018` | **PARTIAL** — replay/HITL matrix incomplete; live PG not run |

### D10-35 / D10-36

| Task | Status | Evidence |
|------|--------|----------|
| D10-35 | **IMPLEMENTED** | Targeted CI, `day10_verify`, 219+ Day10 tests, migration index parity |
| D10-36 | **PENDING** | Awaiting Chief Architect exact-HEAD disposition; full regression log at final SHA |

## 4. Governance

- `founder_approval:false` in `.eduvijna/execution-state.yml` — **unchanged**
- Day **11 LOCKED**; D5-DS01 **#16 OPEN**
- No merge / no production
