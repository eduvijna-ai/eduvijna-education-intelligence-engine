# Day 15 candidate 2 — F01..F10 closure register

| ID | Finding | Repair | Evidence |
|---|---|---|---|
| F01 | Caller harness strings | `harness.py` attestation + catalog match | `test_day15_adversarial.py`, `test_day15_trust_repair.py` |
| F02 | Spoofed actor context | `authorize_actor`, `load_bound_attempt`, scoped queries | `test_day15_trust_repair.py` |
| F03 | Caller fingerprints | Server recompute + persist verify + opaque learner view | `test_day15_core.py`, snapshot tests |
| F04 | Partial max marks | Finalize all issued items; blank for missing | `test_d15_missing_item_scores_blank` |
| F05 | Idempotency/transaction | Nested txn finalize; institution binding | `test_day15_core.py` replay |
| F06 | Mastery policy | Recency window + weighted older events | `test_day15_trust_repair.py` (mastery) |
| F07 | Fake diagnostics | Trusted evidence ref gate; Day10 NOT_READY | verifier diag_count |
| F08 | Handoff/memory | Scoped handoff readiness; org-scoped rebuild API | verifier handoff keys |
| F09 | Migration indexes/FK | 0022 additive FK/index patches | alembic upgrade test in trust_repair |
| F10 | Verifier truth | func.count, production block, scope 36 rows | `day15_verify.py` |