# Day 9 scope map (D9-01)

Maps D9-01…D9-36 to code, tests, and evidence. Day 10+ boundaries are guarded in `app/diagnostic_intelligence/scope_guard.py` and acceptance tests.

| Task | Location | Evidence |
|------|----------|----------|
| D9-01 | `docs/execution/D09-SCOPE-MAP.md` | This file |
| D9-02 | `app/diagnostic_intelligence/` | Framework-independent package; `tests/test_day9_scope.py` |
| D9-03 | `app/diagnostic_intelligence/contracts.py` | Misconception definition models; taxonomy JSON load |
| D9-04 | `app/diagnostic_intelligence/taxonomy_registry.py` | `day9_verify` `taxonomy_resolves` |
| D9-05 | `app/diagnostic_intelligence/contracts.py` | `OptionDiagnosticTag`; orchestration diagnostic payloads |
| D9-06 | `validators/distinctness.py`, `service.py` | `test_day9_close_acceptance.py`; verifier `coverage_complete_tracks_validator` |
| D9-07 | `evidence_policy.py`, `validators/evidence_ref.py`, `grounding.py` | Close tests; SC-R2 `test_day9_sc_r2_acceptance.py`; verifier `foreign_grounding_preflight_rejected` |
| D9-08 | `integration/day7_diagnostic_context.py`, `grounding.py`, `contracts.py` | Shared `measure_composed_evidence_chars`; SC-R3 pack builder; verifier `pack_builder_aggregate_budget_safe` |
| D9-09 | `app/diagnostic_intelligence/contracts.py` | `DistractorDiagnosticResult` |
| D9-10 | `app/diagnostic_intelligence/eligibility.py` | `test_day9_diagnostic.py`, preflight |
| D9-11 | `app/diagnostic_intelligence/correct_option_guard.py` | `test_day9_adversarial.py`; verifier `correct_option_protected` |
| D9-12 | `app/diagnostic_intelligence/candidate_resolver.py` | Service candidate resolution; fixtures |
| D9-13 | `integration/day7_diagnostic_context.py`, `grounding.py` | Citation/revision-bound snippets; SC-R2 preflight tests |
| D9-14 | `app/diagnostic_intelligence/integration/day6_authority.py` | Verifier `day6_authority_survives`; `blocking_day6` scenario |
| D9-15 | `app/diagnostic_intelligence/prompts/registry.py` | Gateway diagnostic prompt versions |
| D9-16 | `app/orchestration/nodes/diagnostic.py` | `GenerationNodeRole.DIAGNOSTIC`; `test_day9_orchestration_preflight.py` |
| D9-17 | `app/diagnostic_intelligence/enrichment.py` | Classification helpers (deterministic validators primary) |
| D9-18 | `app/diagnostic_intelligence/service.py` | `test_day9_service_integrity.py`, `test_day9_diagnostic.py` |
| D9-19 | `validators/signal.py`, `numeric_tokens.py` | SC-R2 decimal guard; verifier `decimal_wrong_answer_signal_rejected` |
| D9-20 | `validators/distinctness.py` | Numeric meaning equivalence + `coverage_complete`; close tests |
| D9-21 | `validators/plausibility.py`, `numeric_tokens.py` | Whole-number plausibility; SC-R2 mixed-severity tests |
| D9-22 | `app/diagnostic_intelligence/validators/factual.py` | Second-correct / `diagnostic_second_correct` |
| D9-23 | `app/diagnostic_intelligence/validators/curriculum_scope.py` | `diagnostic_wrong_subject` adversarial |
| D9-24 | `app/diagnostic_intelligence/validators/evidence_ref.py` | Forged/foreign refs; `test_day9_r4_acceptance.py` |
| D9-25 | `verdict.py` | Severity order REVIEW>REPAIR; item-level propagation; SC-R2 verdict tests |
| D9-26 | `app/orchestration/routing.py`, `nodes/diagnostic.py` | `test_day9_granular_repair.py`, `test_day9_routing.py`; verifier `bounded_repair_works` |
| D9-27 | `diagnostic_audit.py` | `option_traces` in audit payload; verifier `diagnostic_audit_option_traces` |
| D9-28 | `usage.py`, `nodes/diagnostic.py`, `nodes/diagnostic_repair.py` | `token_usage_counts_by_role`, `gateway_ambiguous_by_role`, `diagnostic_tag_repair_calls`; SC-R2 usage tests |
| D9-29 | `app/diagnostic_intelligence/fixtures.py` | `run_positive_fixture_validation`; `day9_verify` clean pass |
| D9-30 | `tests/test_day9_adversarial.py`, `test_day9_close_acceptance.py` | DIAGNOSTIC-stage gateway failures, malformed output, canonical second-correct |
| D9-31 | `tests/test_day9_batch.py` | Multi-item batch; sibling preservation |
| D9-32 | `tests/test_day9_restart.py`, `tests/test_day9_idempotency.py`, `app/diagnostic_intelligence/checkpoint_proof.py` | Interrupted checkpoint retry; idempotent replay/conflict |
| D9-33 | N/A (no new migration) | Taxonomy JSON + existing audit/checkpoint tables; `alembic check`; `tests/test_postgres_compile.py` |
| D9-34 | `app/day9_verify.py`, `tests/test_day9_*.py` | `python -m app.day9_verify --json` |
| D9-35 | `.eduvijna/pytest-targets.txt`, `.github/workflows/targeted-ci.yml` | Targeted CI run #66 on review SHA |
| D9-36 | `docs/execution/D09-D36-ACCEPTANCE-EVIDENCE.md` | **BLOCKED** (Compose + post-closure full regression pending manual review CLEAN) |

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
