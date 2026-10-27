# Day 10 — Scope, implementation and evidence map

Status: **R1 FOCUSED REPAIR** (Chief Architect handoff R1; push pending new HEAD). Source: `docs/execution/D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md`, issue #28.

**R1 deltas (vs `f1a3680`):** `authority.py` fail-closed graph loading; synthetic fixture edges; root-cause path-required PASS; paper competency + partial cognitive targets + fractional counts; orchestration trusted scope + whole-output review gate. Expanded `test_day10_*` (14 tests). D10-22/32/33/36 still PARTIAL/PENDING.

| Task | Approved work | Implementation | Tests / CI | Status |
|---|---|---|---|---|
| D10-01 | Freeze Day-10 scope map | `docs/execution/D10-SCOPE-MAP.md` | `day10_verify` | IMPLEMENTED |
| D10-02 | Reuse Day-2 `ConceptPrerequisite` | `app/prerequisite_intelligence/loader.py` | `test_day10_graph.py` | IMPLEMENTED |
| D10-03 | Versioned graph contracts | `app/prerequisite_intelligence/contracts.py` | `test_day10_graph.py` | IMPLEMENTED |
| D10-04 | Source-backed edge provenance | `authority.py`, `loader.py`, `validators.py`, `fixtures.py` | `test_day10_adversarial.py` | IMPLEMENTED |
| D10-05 | Edge integrity validator | `app/prerequisite_intelligence/validators.py` | `test_day10_graph.py` | IMPLEMENTED |
| D10-06 | Cycle and progression validation | `validators.detect_cycles` | `test_day10_graph.py::test_cycle_detection_flags_error` | IMPLEMENTED |
| D10-07 | Curriculum and tenant scope isolation | `loader.py`, `validators.validate_scope_isolation` | `test_day10_adversarial.py` | IMPLEMENTED |
| D10-08 | Versioned graph assembly / lifecycle | `loader.load_prerequisite_graph_snapshot` | `day10_verify` checksum | IMPLEMENTED |
| D10-09 | Bounded graph traversal | `app/prerequisite_intelligence/traversal.py` | `test_day10_graph.py` | IMPLEMENTED |
| D10-10 | Graph quality audit | `app/prerequisite_intelligence/audit.py` | `day10_verify` graph_quality_pass | IMPLEMENTED |
| D10-11 | Diagnostic request contract | `app/root_cause_intelligence/contracts.py` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-12 | Misconception → concept mapping | `mapping_registry.py`, `data/root_cause_mapping_v1.json` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-13 | Eligibility preflight | `app/root_cause_intelligence/preflight.py` | `test_day10_root_cause.py::test_correct_option_tag_is_blocked` | IMPLEMENTED |
| D10-14 | Candidate prerequisite resolver | `ranking.py` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-15 | Bounded backward traversal | `traversal.bounded_ancestor_paths` | `day10_verify` alternate_prerequisite_paths | IMPLEMENTED |
| D10-16 | Deterministic hypothesis ranking | `ranking.rank_root_cause_hypotheses` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-17 | Alternative hypotheses | `RootCauseHypothesis.alternatives` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-18 | Contradiction / uncertainty | `service.py` verdict policy | `day10_verify` root_cause_verdict | IMPLEMENTED |
| D10-19 | LO/competency consistency | mapping + Day9 taxonomy codes | boundary via Day9 tests in CI | PARTIAL |
| D10-20 | Day-7 provenance / tenant | `service.py` unauthorized source | `test_day10_adversarial.py` | IMPLEMENTED |
| D10-21 | Structured result/verdict/audit | `RootCauseResult` | `day10_verify` | IMPLEMENTED |
| D10-22 | Day-8/9 integration | `orchestration/nodes/root_cause.py`, routing | manual / follow-up test | PARTIAL |
| D10-23 | Paper distribution request/result | `app/paper_distribution/contracts.py` | `test_day10_paper_distribution.py` | IMPLEMENTED |
| D10-24 | Cognitive actual distribution | `evaluator.py` | `test_demo_paper_matches_20_20_40_10_10` | IMPLEMENTED |
| D10-25 | Competency distribution | `evaluator.py` | `test_fractional_multi_label_conserves_denominator` | IMPLEMENTED |
| D10-26 | Multi-label policy | `enums.MultiLabelPolicy` | paper tests | IMPLEMENTED |
| D10-27 | Count vs mark-weighted | `DimensionSummary` | `day10_verify` | IMPLEMENTED |
| D10-28 | Generic target policy | `DistributionTarget` | mismatch paper test | IMPLEMENTED |
| D10-29 | Integer target reconciliation | `_reconcile_exact_counts` | demo paper PASS | IMPLEMENTED |
| D10-30 | Distribution audit verdict | `PaperDistributionResult` | `test_mismatched_target_fails_paper_not_items` | IMPLEMENTED |
| D10-31 | Deterministic positive fixtures | `prerequisite_intelligence/fixtures.py`, `paper_distribution/fixtures.py` | `day10_verify` | IMPLEMENTED |
| D10-32 | Adversarial fixtures | `test_day10_adversarial.py` | targeted pytest | PARTIAL |
| D10-33 | Batch/replay/SQLite-PG | SQLite tests only; no new migrations | existing portability | PARTIAL |
| D10-34 | `app.day10_verify` | `app/day10_verify.py` | targeted CI step | IMPLEMENTED |
| D10-35 | Targeted CI / evidence map | `.eduvijna/pytest-targets.txt`, `targeted-ci.yml` | GitHub CI pending push | IMPLEMENTED |
| D10-36 | Final acceptance | **STOP — handback for Chief Architect review** | full regression deferred | PENDING |

## Governance gates

- D10 implementation authorized; `founder_approval:false` until D10-36 signoff. Day11 LOCKED.
- No new Alembic migrations (reuse Day-2 `concept_prerequisites`).
- Founder localhost/Docker UAT deferred; not passed.
- D5-DS01 / issue #16 OPEN.
- No AnythingLLM/provider calls in Day-10 paths.
