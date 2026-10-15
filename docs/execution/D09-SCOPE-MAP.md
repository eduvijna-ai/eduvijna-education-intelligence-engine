# Day 9 scope map (D9-01)

Maps D9-01…D9-36 to code, tests, and evidence. Day 10+ boundaries are guarded in `app/diagnostic_intelligence/scope_guard.py` and acceptance tests.

| Task | Location | Evidence |
|------|----------|----------|
| D9-01 | `docs/execution/D09-SCOPE-MAP.md` | This file |
| D9-02 | `app/diagnostic_intelligence/` | Framework-independent package |
| D9-03 | `app/diagnostic_intelligence/contracts.py` | Misconception definition models |
| D9-04 | `app/diagnostic_intelligence/taxonomy_registry.py` | Versioned registry loader |
| D9-05 | `app/diagnostic_intelligence/contracts.py` | Option-level diagnostic tag |
| D9-06 | `app/diagnostic_intelligence/contracts.py` | Diagnostic coverage summary |
| D9-07 | `app/diagnostic_intelligence/integration/day7_evidence.py` | Evidence/provenance validation |
| D9-08 | `app/diagnostic_intelligence/contracts.py` | Authoring request |
| D9-09 | `app/diagnostic_intelligence/contracts.py` | Diagnostic result models |
| D9-10 | `app/diagnostic_intelligence/eligibility.py` | Question-type eligibility |
| D9-11 | `app/diagnostic_intelligence/correct_option_guard.py` | Correct-option integrity |
| D9-12 | `app/diagnostic_intelligence/candidate_resolver.py` | Scoped misconception candidates |
| D9-13 | `app/diagnostic_intelligence/integration/day7_evidence.py` | Day 7 context pack integration |
| D9-14 | `app/diagnostic_intelligence/integration/day6_authority.py` | Day 6 blocking guard |
| D9-15 | `app/diagnostic_intelligence/prompts/registry.py` | Versioned diagnostic prompts |
| D9-16 | `app/orchestration/nodes/diagnostic.py` | Day 8 gateway reuse |
| D9-17 | `app/diagnostic_intelligence/enrichment.py` | Distractor proposal/classification |
| D9-18 | `app/diagnostic_intelligence/service.py` | Option-level tagging |
| D9-19 | `app/diagnostic_intelligence/validators/signal.py` | Signal/text alignment |
| D9-20 | `app/diagnostic_intelligence/validators/distinctness.py` | Misconception distinctness |
| D9-21 | `app/diagnostic_intelligence/validators/plausibility.py` | Plausibility policy |
| D9-22 | `app/diagnostic_intelligence/validators/factual.py` | Second-correct guard |
| D9-23 | `app/diagnostic_intelligence/validators/curriculum_scope.py` | Curriculum scope |
| D9-24 | `app/diagnostic_intelligence/validators/evidence_ref.py` | Evidence ref validation |
| D9-25 | `app/diagnostic_intelligence/verdict.py` | Unified diagnostic verdict |
| D9-26 | `app/orchestration/routing.py`, `nodes/diagnostic.py` | Bounded Day 8 repair integration |
| D9-27 | `app/diagnostic_intelligence/audit.py` | Structured diagnostic audit events |
| D9-28 | `app/orchestration/nodes/diagnostic.py` | Usage/latency via gateway |
| D9-29 | `app/diagnostic_intelligence/fixtures.py` | Positive deterministic fixtures |
| D9-30 | `tests/test_day9_adversarial.py` | Adversarial fixtures |
| D9-31 | `tests/test_day9_batch.py` | Multi-item batch tests |
| D9-32 | `tests/test_day9_idempotency.py` | Restart/idempotency tests |
| D9-33 | N/A (taxonomy JSON + orchestration audit) | No new schema migration |
| D9-34 | `app/day9_verify.py`, `tests/test_day9_*.py` | Founder verifier |
| D9-35 | `.eduvijna/pytest-targets.txt`, CI | Targeted Day 9 suite |
| D9-36 | Final acceptance gate | Deferred until Founder review |

## Explicitly out of scope (Day 10+)

- Prerequisite knowledge graph / root-cause inference (Day 10)
- Learner diagnosis profile / mastery / adaptation (Days 15–16)
- Remediation plans (Day 16)
- Exam-specific blueprint distribution (Days 11–14)
- Public REST, MCP, async jobs (Day 17)
- React UI (Day 18)
