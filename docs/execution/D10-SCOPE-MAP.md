# Day 10 — Scope, implementation and evidence map

Status: **R6 FOCUSED REPAIR** (Chief Architect handoff R6). Source: `docs/execution/D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md`, issue #28.

**R6 deltas (vs `4e449677`):** Day6 `validated_items` on persist (`kind=day6_validation`); paper trust rejects `paper_distribution` audits and fail-closed per-item binding; active paper-distribution target policy registry; `PaperExecutionContext` for tenant-scoped audit; session-backed graph checksum/canonical reload (`graph_verify.py`); production loader blocks unbound synthetic/inferred edges; option citation strict binding + Day9 trace `evidence_refs` match; expanded `test_day10_r6_trust.py`. D10-22/32/33/36 still PARTIAL/PENDING (no full LangGraph replay/HITL matrix).

| Task | Approved work | Implementation | Tests / CI | Status |
|---|---|---|---|---|
| D10-01 | Freeze Day-10 scope map | `docs/execution/D10-SCOPE-MAP.md` | `day10_verify` | IMPLEMENTED |
| D10-02 | Reuse Day-2 `ConceptPrerequisite` | `app/prerequisite_intelligence/loader.py` | `test_day10_graph.py` | IMPLEMENTED |
| D10-03 | Versioned graph contracts | `app/prerequisite_intelligence/contracts.py` | `test_day10_graph.py` | IMPLEMENTED |
| D10-04 | Source-backed edge provenance | `authority.py`, `loader.py`, `validators.py`, `fixtures.py` | `test_day10_adversarial.py` | IMPLEMENTED |
| D10-05 | Edge integrity validator | `app/prerequisite_intelligence/validators.py` | `test_day10_graph.py` | IMPLEMENTED |
| D10-06 | Cycle and progression validation | `validators.detect_cycles` | `test_day10_graph.py::test_cycle_detection_flags_error` | IMPLEMENTED |
| D10-07 | Curriculum and tenant scope isolation | `loader.py` ancestry + `graph_verify.py` | `test_day10_graph.py`, `test_day10_r6_trust.py` | IMPLEMENTED |
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
| D10-19 | LO/competency consistency | Day6 per-item trust + paper guards | `test_day10_r6_trust.py` | PARTIAL |
| D10-20 | Day-7 provenance / tenant | `root_cause_trust.py` citation binding | `test_day10_r6_trust.py` | IMPLEMENTED |
| D10-21 | Structured result/verdict/audit | `RootCauseResult` | `day10_verify` | IMPLEMENTED |
| D10-22 | Day-8/9 integration | `root_cause.py` + graph compile | `test_day10_orchestration.py`, `test_day10_r6_trust.py` | PARTIAL |
| D10-23 | Paper distribution request/result | `app/paper_distribution/contracts.py` | `test_day10_paper_distribution.py` | IMPLEMENTED |
| D10-24 | Cognitive actual distribution | `evaluator.py` | `test_demo_paper_matches_20_20_40_10_10` | IMPLEMENTED |
| D10-25 | Competency distribution | `evaluator.py` | `test_fractional_multi_label_conserves_denominator` | IMPLEMENTED |
| D10-26 | Multi-label policy | `enums.MultiLabelPolicy` | paper tests | IMPLEMENTED |
| D10-27 | Count vs mark-weighted | `DimensionSummary` | `day10_verify` | IMPLEMENTED |
| D10-28 | Generic target policy | `target_policy_registry.py` | `test_day10_r6_trust.py` | IMPLEMENTED |
| D10-29 | Integer target reconciliation | `_reconcile_exact_counts` | demo paper PASS | IMPLEMENTED |
| D10-30 | Distribution audit verdict | `paper_distribution/audit.py` + session path | `test_day10_r6_trust.py` tenant isolation | IMPLEMENTED |
| D10-31 | Deterministic positive fixtures | `prerequisite_intelligence/fixtures.py`, `paper_distribution/fixtures.py` | `day10_verify` | IMPLEMENTED |
| D10-32 | Adversarial fixtures | `test_day10_adversarial.py`, `test_day10_r6_trust.py` | targeted pytest | PARTIAL |
| D10-33 | Batch / replay / HITL | orchestration idempotency (Day8) only | `test_day10_r6_trust.py` graph compile | PARTIAL |
| D10-34 | `day10_verify` harness | `app/day10_verify.py` | CI verifier step | IMPLEMENTED |
| D10-35 | SQLite / Alembic portability | existing migrations unchanged | CI backend-targeted | IMPLEMENTED |
| D10-36 | Founder acceptance evidence | — | — | PENDING |
