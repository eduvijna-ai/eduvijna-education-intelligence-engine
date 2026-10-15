# Day 9 — D9-36 final acceptance evidence

**Status:** Pending Founder signoff (engineering evidence collected on frozen candidate).

| Field | Value |
|-------|--------|
| Manual code review CLEAN SHA | `eede5d67048502211d867ba45390b43c4f820f1d` |
| Acceptance candidate SHA (code) | `eede5d67048502211d867ba45390b43c4f820f1d` |
| Docs evidence SHA (after scope-map) | See PR handback `git rev-parse HEAD` |
| PR | #27 `feature/day9-diagnostic-distractor-intelligence` → `develop` (Draft, unmerged) |
| Targeted CI (review SHA) | Run **#66** / `38729926335` — SUCCESS |

## D9-36 checklist

| Step | Result | Notes |
|------|--------|-------|
| Evidence map updated | See `D09-SCOPE-MAP.md` | D9-27 audit path, D9-32 restart proof, D9-36 pending Founder |
| `EDUVIJNA_CANDIDATE_SHA` | Set to acceptance candidate | Verifiers use explicit candidate |
| Full `pytest tests/` | See regression section below | One historical regression at frozen SHA |
| `python -m app.day8_verify` | PASS | With candidate SHA |
| `python -m app.day9_verify --json` | `ok: true` | Structured checks in PR handback |
| Compose smoke | **BLOCKED** on Cloud Agent VM (`docker` not installed) | Targeted CI `compose-smoke` job when enabled on GitHub |
| Migrations / Postgres | See persistence section | No Day-9 DDL; Alembic check + compile test |

## Full historical regression

Command (from `backend/`):

```bash
python -m pytest tests -q --tb=no
```

Environment: Cloud Agent VM, Python 3.12, `backend/.venv`, SQLite in-memory/default test DBs.

**Result:** PASS — `1784` collected, **0 failed** (exit code 0). Command output did not report skips/xfails under `-q`; treat as full pass unless a future run shows otherwise.

Wall time ~28 min on Cloud Agent VM (Python 3.12, `backend/.venv`). Log: `d9-36-full-pytest.log`.

## Founder verifiers (JSON)

Run:

```bash
export EDUVIJNA_CANDIDATE_SHA=<acceptance-candidate-40-char-sha>
cd backend && python -m app.day8_verify && python -m app.day9_verify --json
```

`day9_verify` demonstrates: taxonomy resolve, option tags, correct-option protection, signal/distinctness/provenance, Day-6 block, tenant isolation (DB ownership), `RequestCapturingGateway` foreign-injection prompt proof, HITL diagnostic review/edit, marks edit forbidden, bounded repair, forged evidence reject, checkpoint explicit retry (`checkpoint_proof.py`), idempotent replay/conflict, diagnostic audit on `OrchestrationAuditEvent`, scope guards, candidate SHA match.

## D9-29…D9-35 demonstration trace (synthetic MCQ)

Positive path (no live LLM — `FakeGenerationGateway` + fixtures):

1. **Canonical item + Day 7 context** — `seed_day8_fixtures` + `resolve_context` / `KnowledgeContextPack` (`test_day9_diagnostic.py`, `day9_verify` clean pass).
2. **Taxonomy candidates** — `resolve_misconception_candidates` (`candidate_resolver.py`).
3. **Option-level tags** — `DiagnosticIntelligenceService` + `nodes/diagnostic.py` gateway role `DIAGNOSTIC`.
4. **Validators** — signal, distinctness, plausibility, factual, curriculum, evidence_ref, `result_integrity` (`test_day9_r4`–`r7`, `test_day9_adversarial.py`).
5. **Day 6 authority** — `integration/day6_authority.py`; blocked scenario `blocking_day6` → `OrchestrationRunStatus.FAILED`.
6. **Bounded repair** — `diagnostic_repair_then_pass` scenario; `test_day9_granular_repair.py`, `test_day9_batch.py` (one-item repair in 2-item batch).
7. **Approved result** — `diagnostic_clean_pass` → `COMPLETED` with `diagnostic_results` + audit refs.

Negative cases (representative tests / verifier):

| Case | Evidence |
|------|----------|
| Correct option mislabeled | `diagnostic_correct_mislabeled` / `test_day9_adversarial.py` |
| Unknown / inactive code | `diagnostic_unknown_code`, `diagnostic_inactive` / verifier `unknown_code_rejected` |
| Cross-scope / tenant refs | `test_day9_r4_acceptance.py`, `day9_tenant_fixtures`, verifier `tenant_isolation_enforced` |
| Duplicate misconception / redundant option | `distinctness.py`, `test_day9_r7`, verifier distinctness/redundant checks |
| Second-correct ambiguity | `diagnostic_second_correct` / factual validator |
| Injection evidence (untrusted) | `injection_evidence` scenario + `injection_evidence_control`; foreign metadata cannot enter prompts (`RequestCapturingGateway`) |
| Gateway timeout/error | `test_day8_*` gateway error paths; `checkpoint_proof` retry |
| Repair bound | `max_repairs` / repair exhaustion Day 8 patterns |
| Restart / replay | `test_day9_restart.py`, `test_day9_idempotency.py`, `checkpoint_proof.prove_interrupted_diagnostic_checkpoint_restart` |

Runtime guarantee: orchestration uses `GenerationGateway` protocol only (`FakeGenerationGateway` / `AnythingLLMGenerationGateway`); no direct provider SDK in business services (`day8_verify` `no_direct_provider_path`).

## Persistence / compatibility (D9-33)

- **New Day-9 tables:** None. Diagnostic taxonomy is versioned JSON; durable events use existing `OrchestrationAuditEvent` (`app/orchestration/diagnostic_audit.py`) and Day-8 checkpoint/idempotency tables.
- **SQLite:** Fresh `alembic upgrade head` + `alembic check` on acceptance candidate (head `20261015_0014`).
- **PostgreSQL:** `tests/test_postgres_compile.py` (DDL/static compile harness in CI); no live Postgres instance in this acceptance VM unless separately provisioned.

## Governance

- PR #27 remains **Draft**; **not merged**.
- Day 10 remains **LOCKED** in `.eduvijna/execution-state.yml`; `founder_approval` not set for Day 9.
- D5-DS01 / issue #16 unchanged.
- No Codex review requested.

## Founder acceptance

Engineering status after evidence collection: **READY FOR FOUNDER ACCEPTANCE** when full regression and compose sections are green; otherwise **FAILED** or **BLOCKED** as noted in PR handback.
