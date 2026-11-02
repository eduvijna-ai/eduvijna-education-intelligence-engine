# Day 10 — Scope, implementation and evidence map

Status: **R21 FOCUSED REPAIR** (Chief Architect handoff R21). Source: `docs/execution/D10-PREREQUISITES-ROOT-CAUSE-DIAGNOSTICS.md`, issue #28.

**R21 deltas (vs `9bf7bfc`):** compiled **`OrchestrationService.run`** production-scope proof + HITL/replay in **`test_day10_r21_trust.py`** (D10-19/22/32/33 still **PARTIAL** until PASS+hypothesis matrix complete); **Day6 reuse** version/scope/source-revision canonical hash in **`day6_reuse.py`** + **`canonical_mapping.py`**; **mandatory policy claim** locator/lifecycle read-path in **`mandatory_policy_claim_authority.py`**; **mapping overlay read** on configured **`SOURCE_STORAGE_DIR`** (JSON upload); Founder decision doc **`D10-R21-POLICY-MAPPING-AUTH-FOUNDER-DECISION.md`** (options A/B — **not chosen**). D10-12/28/29 remain **PARTIAL**; D10-36 **PENDING**.

**R20 deltas (vs `5bc70af`):** **`RootCauseIntelligenceService.analyze`** uses **`domain_session`** for policy/graph/Day6/source lookups and **`control_session`** only for Day9 audit; file-backed SQLite orchestration proof in **`test_day10_r20_trust.py`**; Day6 reuse keyed on **`canonical_hash`** + persisted-run lookup/idempotency; source integrity uses **`SourceRevision.ingestion_method`** only; **`approve_mandatory_policy_claim`** validates persisted **`PolicyRule`**, revision binding, source approval, actor, and board official trust tier. D10-12/19/22/28/29/32/33 remain **PARTIAL**; D10-36 **PENDING**.

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
| D10-12 | Misconception → concept mapping | `mapping_registry.py`, `mapping_claim_authority.py`, `mapping_evidence.py` | `test_day10_r17_trust.py` (span integrity, curator AdminActor, A/B scope) | PARTIAL |
| D10-13 | Eligibility preflight | `app/root_cause_intelligence/preflight.py` | `test_day10_root_cause.py::test_correct_option_tag_is_blocked` | IMPLEMENTED |
| D10-14 | Candidate prerequisite resolver | `ranking.py` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-15 | Bounded backward traversal | `traversal.bounded_ancestor_paths` | `day10_verify` alternate_prerequisite_paths | IMPLEMENTED |
| D10-16 | Deterministic hypothesis ranking | `ranking.rank_root_cause_hypotheses` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-17 | Alternative hypotheses | `RootCauseHypothesis.alternatives` | `test_day10_root_cause.py` | IMPLEMENTED |
| D10-18 | Contradiction / uncertainty | `service.py` verdict policy | `day10_verify` root_cause_verdict | IMPLEMENTED |
| D10-19 | LO/competency consistency | `day6_binding_verify.py` production fail-closed | `test_day10_r17_trust.py`, `day10_day6_binding.py` | PARTIAL |
| D10-20 | Day-7 provenance / tenant | `root_cause_trust.py` citation binding | `test_day10_r6_trust.py` | IMPLEMENTED |
| D10-21 | Structured result/verdict/audit | `RootCauseResult` | `day10_verify` | IMPLEMENTED |
| D10-22 | Day-8/9 integration | `root_cause.py` + graph compile + HITL route | `test_day10_r21_trust.py` compiled run (partial PASS/hypothesis matrix) | PARTIAL |
| D10-23 | Paper distribution request/result | `app/paper_distribution/contracts.py` | `test_day10_paper_distribution.py` | IMPLEMENTED |
| D10-24 | Cognitive actual distribution | `evaluator.py` | `test_demo_paper_matches_20_20_40_10_10` | IMPLEMENTED |
| D10-25 | Competency distribution | `evaluator.py` | `test_fractional_multi_label_conserves_denominator` | IMPLEMENTED |
| D10-26 | Multi-label policy | `enums.MultiLabelPolicy` | paper tests | IMPLEMENTED |
| D10-27 | Count vs mark-weighted | `DimensionSummary` | `day10_verify` | IMPLEMENTED |
| D10-28 | Generic target policy | `mandatory_policy_resolver.py` conflict + scope errors | `test_day10_r18_trust.py` (board exact_count/percent enforcement) | PARTIAL |
| D10-29 | Integer target reconciliation | `reconcile_exact_counts` + policy merge | `test_day10_r9_trust.py` | PARTIAL |
| D10-30 | Distribution audit verdict | `paper_distribution/audit.py` + session path | `test_day10_r6_trust.py` tenant isolation | IMPLEMENTED |
| D10-31 | Deterministic positive fixtures | `prerequisite_intelligence/fixtures.py`, `paper_distribution/fixtures.py` | `day10_verify` | IMPLEMENTED |
| D10-32 | Adversarial fixtures | `test_day10_adversarial.py`, `test_day10_r6_trust.py` | targeted pytest | PARTIAL |
| D10-33 | Batch / replay / HITL | HITL → `root_cause_enrich` routing; replay idempotency | `test_day10_r21_trust.py` gateway/audit replay | PARTIAL |
| D10-34 | `day10_verify` harness | `app/day10_verify.py` | CI verifier step | IMPLEMENTED |
| D10-35 | SQLite / Alembic portability | existing migrations unchanged | `test_day10_r14_trust.py` Alembic head + PG DDL compile (live PG untested) | PARTIAL |
| D10-36 | Founder acceptance evidence | — | — | PENDING |
