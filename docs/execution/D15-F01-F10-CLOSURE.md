# Day 15 candidate 3 — F01..F10 / R3-01..R3-06 closure register

| ID | Finding | Repair | Evidence |
|---|---|---|---|
| F01 / R3-01 | Public attestation + shared session | `harness_runtime.py` isolated DB + `gate.py` session flag; service rejects ordinary sessions | `test_ordinary_session_rejects_create`, `day15_verify` `ordinary_session_rejected` |
| F02 / R3-01 | Membership-only auth | Harness binding on attempts; cross-tenant tests unchanged | `test_cross_tenant_learner_view_blocked` |
| F03 / R3-03 | Incomplete row binding | `question_id` + sequence in `verify_item_matches_persisted_row` | `test_day15_core.py` learner view |
| F04 / R3-03 | Scoring policy drift | Explicit `scoring@v1-multi_partial`; numeric finiteness guards | scoring module + finalize path |
| F05 / R3-02 | Caller commit/idempotency | Flush-only service; strict cached outcome verify | replay tests, idempotency event count |
| F06 / R3-04 | BLANK in mastery | Exclude BLANK from evidence window | `test_mastery_blank_excluded_from_support` |
| F07 / R3-04 | Diagnostic breadth | Day10 NOT_READY unchanged; harness evidence ref only in catalog | verifier `diag_count` bounded |
| F08 / R3-05 | Actionable handoff | `build_day16_handoff` unconditional NOT_READY empty | `day15_verify` handoff assertions |
| F09 / R3-06 | Alembic path | Module-relative `alembic.ini` in trust test | `test_alembic_upgrade_head_sqlite` |
| F10 / R3-06 | Verifier truth | Isolated harness run; no actionable handoff requirement | `python -m app.day15_verify --json` |

## Commands (candidate 3)

```text
pytest tests/test_day15_*.py → 21 passed
ruff check app tests → pass
mypy app → pass
python -m app.day15_verify --json @ HEAD → ok: true
```

D15-36 remains **NOT_STARTED**. Ledger: **0 PASS / 35 PARTIAL / 1 NOT_STARTED** (no inflated PASS).