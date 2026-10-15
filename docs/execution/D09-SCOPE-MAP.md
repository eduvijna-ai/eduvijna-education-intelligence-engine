# Day 9 scope map (D9-01)

Maps D9-01…D9-36 to code, tests, and evidence. Day 10+ boundaries are guarded in `app/diagnostic_intelligence/scope_guard.py` and acceptance tests.

| Task | Location | Evidence |
|------|----------|----------|
| D9-01 | `docs/execution/D09-SCOPE-MAP.md` | This file |
| D9-02 | `app/diagnostic_intelligence/` | Framework-independent package; `tests/test_day9_scope.py` |
| D9-03 | `app/diagnostic_intelligence/contracts.py` | Misconception definition models; taxonomy JSON load |
| D9-04 | `app/diagnostic_intelligence/taxonomy_registry.py` | `day9_verify` `taxonomy_resolves` |
| D9-05 | `app/diagnostic_intelligence/contracts.py` | `OptionDiagnosticTag`; orchestration diagnostic payloads |
| D9-06 | `app/diagnostic_intelligence/contracts.py` | Coverage summary on diagnostic results |
| D9-07 | `app/diagnostic_intelligence/integration/day7_evidence.py` | `validators/evidence_ref.py`, `integration/revision_tenancy.py` |
| D9-08 | `app/diagnostic_intelligence/contracts.py` | `DiagnosticAuthoringRequest` |
| D9-09 | `app/diagnostic_intelligence/contracts.py` | `DistractorDiagnosticResult` |
| D9-10 | `app/diagnostic_intelligence/eligibility.py` | `test_day9_diagnostic.py`, preflight |
| D9-11 | `app/diagnostic_intelligence/correct_option_guard.py` | `test_day9_adversarial.py`; verifier `correct_option_protected` |
| D9-12 | `app/diagnostic_intelligence/candidate_resolver.py` | Service candidate resolution; fixtures |
| D9-13 | `app/diagnostic_intelligence/integration/day7_evidence.py` | Orchestration `resolve_context`; Day 7 retrieval in tests |
| D9-14 | `app/diagnostic_intelligence/integration/day6_authority.py` | Verifier `day6_authority_survives`; `blocking_day6` scenario |
| D9-15 | `app/diagnostic_intelligence/prompts/registry.py` | Gateway diagnostic prompt versions |
| D9-16 | `app/orchestration/nodes/diagnostic.py` | `GenerationNodeRole.DIAGNOSTIC`; `test_day9_orchestration_preflight.py` |
| D9-17 | `app/diagnostic_intelligence/enrichment.py` | Classification helpers (deterministic validators primary) |
| D9-18 | `app/diagnostic_intelligence/service.py` | `test_day9_service_integrity.py`, `test_day9_diagnostic.py` |
| D9-19 | `app/diagnostic_intelligence/validators/signal.py` | `test_day9_r5_acceptance.py`, `test_day9_r6_acceptance.py`; verifier signal checks |
| D9-20 | `app/diagnostic_intelligence/validators/distinctness.py` | `test_day9_r4_acceptance.py`, `test_day9_r7_acceptance.py` |
| D9-21 | `app/diagnostic_intelligence/validators/plausibility.py` | Service validation path |
| D9-22 | `app/diagnostic_intelligence/validators/factual.py` | Second-correct / `diagnostic_second_correct` |
| D9-23 | `app/diagnostic_intelligence/validators/curriculum_scope.py` | `diagnostic_wrong_subject` adversarial |
| D9-24 | `app/diagnostic_intelligence/validators/evidence_ref.py` | Forged/foreign refs; `test_day9_r4_acceptance.py` |
| D9-25 | `app/diagnostic_intelligence/verdict.py` | Unified status/repair/review routing |
| D9-26 | `app/orchestration/routing.py`, `nodes/diagnostic.py` | `test_day9_granular_repair.py`, `test_day9_routing.py`; verifier `bounded_repair_works` |
| D9-27 | `app/orchestration/diagnostic_audit.py`, `OrchestrationAuditEvent` | `tests/test_day9_audit.py`; verifier `diagnostic_audit_persisted` (not removed `audit.py`) |
| D9-28 | `app/orchestration/nodes/diagnostic.py` | Gateway `call_context` / usage on `GenerationResponse` |
| D9-29 | `app/diagnostic_intelligence/fixtures.py` | `run_positive_fixture_validation`; `day9_verify` clean pass |
| D9-30 | `tests/test_day9_adversarial.py` | Unknown/inactive/foreign/injection/malformed/gateway cases |
| D9-31 | `tests/test_day9_batch.py` | Multi-item batch; sibling preservation |
| D9-32 | `tests/test_day9_restart.py`, `tests/test_day9_idempotency.py`, `app/diagnostic_intelligence/checkpoint_proof.py` | Interrupted checkpoint retry; idempotent replay/conflict |
| D9-33 | N/A (no new migration) | Taxonomy JSON + existing audit/checkpoint tables; `alembic check`; `tests/test_postgres_compile.py` |
| D9-34 | `app/day9_verify.py`, `tests/test_day9_*.py` | `python -m app.day9_verify --json` |
| D9-35 | `.eduvijna/pytest-targets.txt`, `.github/workflows/targeted-ci.yml` | Targeted CI run #66 on review SHA |
| D9-36 | `docs/execution/D09-D36-ACCEPTANCE-EVIDENCE.md` | **Pending Founder signoff** — full regression + handback on frozen SHA |

## Explicitly out of scope (Day 10+)

- Prerequisite knowledge graph / root-cause inference (Day 10)
- Learner diagnosis profile / mastery / adaptation (Days 15–16)
- Remediation plans (Day 16)
- Exam-specific blueprint distribution (Days 11–14)
- Public REST, MCP, async jobs (Day 17)
- React UI (Day 18)

## Untested / environment-limited (D9-36)

| Item | Label |
|------|--------|
| Live AnythingLLM / production gateway | Not required for Day 9 acceptance (fake gateway + adapter boundary) |
| Live PostgreSQL instance | DDL compile test only unless CI Postgres job run separately |
| Docker Compose smoke on Cloud Agent VM | **BLOCKED** when `docker` unavailable; targeted CI compose job is authoritative when enabled |
| Full historical `pytest` | Required once per D9-36 at acceptance SHA (see acceptance evidence doc) |
