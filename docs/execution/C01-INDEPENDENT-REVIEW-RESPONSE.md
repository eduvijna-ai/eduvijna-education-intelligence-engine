# C01-A independent review response (candidate 2)

| ID | Severity | Response |
| --- | --- | --- |
| **F01** | CRITICAL | Corrected Gate B: `active_slot` is **INTEGER**; portable `(active AND slot=1) OR (inactive AND slot IS NULL)`; inventory in `C01-CHECK-CONSTRAINT-INVENTORY.md`; disposable probes in harness transcripts. Expansion to `0006`+model requires **separate Founder approval**. |
| **F02** | CRITICAL | Replaced unsafe PG/SQLite predicate proposals with **type-preserving** JSON boolean checks; documented SQLite `json_extract` ambiguity and untrusted applied `0021` on SQLite; abort-only disposition. |
| **F03** | HIGH | Replaced brittle `run_gate_a_diagnostics.sh` with guarded `c01_gate_a_harness.py`; unique run ids; raw psql/alembic transcripts; separated trials; corrected SQLSTATE notes (`boolean = integer` vs assignment). |
| **F04** | HIGH | Overlay builder keys foundation rows (`D1-DOD-*`, `D3-R11/12`); parent links on omissions; PR31 head **`0018`** corrected; held SHA-256 recorded. |
| **F05** | HIGH | Scope map downgraded to PARTIAL where reproducibility/design incomplete; CI `45572420611` cited separately from diagnostics; Gate B escalation protocol added. |

**Not done (authorized holds):** no migration/app/CI edits; no Gate B; no data remediation.