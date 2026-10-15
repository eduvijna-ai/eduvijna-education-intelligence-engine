# Day 8 scope map (D8-01)

Maps D8-01…D8-36 to code, tests, and evidence. Day 9+ boundaries are guarded in `app/orchestration/scope_guard.py` and acceptance tests.

| Task | Location | Evidence |
|------|----------|----------|
| D8-01 | `docs/execution/D08-SCOPE-MAP.md` | This file |
| D8-02 | `app/orchestration/` | Package importable without FastAPI |
| D8-03 | `app/orchestration/state.py` | Typed graph state + reducers |
| D8-04 | `app/orchestration/gateway/protocol.py` | Generation gateway protocol |
| D8-05 | `app/orchestration/gateway/anythingllm.py` | AnythingLLM HTTP generation adapter |
| D8-06 | `app/orchestration/gateway/fake.py` | Deterministic fake gateway |
| D8-07 | `app/orchestration/prompts/registry.py` | Versioned prompt registry |
| D8-08 | `app/orchestration/contracts.py` | Request validation |
| D8-09 | `app/orchestration/contracts.py` | Result models |
| D8-10 | `app/orchestration/idempotency.py` | Run identity + idempotency |
| D8-11 | `app/orchestration/graph.py` | StateGraph builder + DI |
| D8-12 | `app/orchestration/nodes/resolve_scope.py` | Curriculum/exam resolver |
| D8-13 | `app/orchestration/nodes/resolve_context.py` | Day 7 context resolver |
| D8-14 | `app/orchestration/nodes/plan.py` | Generic generation planner |
| D8-15 | `app/orchestration/nodes/author.py` | Question author |
| D8-16 | `app/orchestration/nodes/solver.py` | Independent solver |
| D8-17 | `app/orchestration/math_tools.py` | Deterministic math boundary |
| D8-18 | `app/orchestration/nodes/reviewers.py` | Pattern reviewer |
| D8-19 | `app/orchestration/nodes/reviewers.py` | Curriculum reviewer |
| D8-20 | `app/orchestration/nodes/reviewers.py` | Educational reviewer + Day 6 |
| D8-21 | `app/orchestration/nodes/validate.py` | Deterministic validator aggregation |
| D8-22 | `app/orchestration/duplicate.py` | Duplicate/similarity validation |
| D8-23 | `app/orchestration/contracts.py` | Unified review verdict |
| D8-24 | `app/orchestration/nodes/repair.py` | Repair planner |
| D8-25 | `app/orchestration/routing.py` | Bounded repair router |
| D8-26 | `app/orchestration/nodes/whole_output.py` | Whole-output validator |
| D8-27 | `app/orchestration/enums.py` | Terminal state taxonomy |
| D8-28 | `app/orchestration/checkpoint.py` | Checkpointer abstraction |
| D8-29 | `app/orchestration/service.py` | Resume/restart semantics |
| D8-30 | `app/orchestration/nodes/human_gate.py` | Human-in-the-loop hook |
| D8-31 | `app/orchestration/audit.py` | Graph execution audit |
| D8-32 | `app/orchestration/usage.py` | Usage/latency accounting |
| D8-33 | `app/orchestration/fixtures.py` | Positive fixtures |
| D8-34 | `tests/test_day8_adversarial.py` | Adversarial fixtures |
| D8-35 | `app/day8_verify.py`, `tests/test_day8_*.py` | Founder verifier |
| D8-36 | CI + `day8_verify` | Final acceptance gate |

## Explicitly out of scope (Day 9+)

- Misconception-driven distractor taxonomy (Day 9)
- Prerequisite / root-cause diagnostics (Day 10)
- Exam-specific blueprint planners (Days 11–14)
- Learner adaptation / long-term memory Store (Days 15–16)
- Public REST, MCP, async job worker (Day 17)
- React UI (Day 18)
