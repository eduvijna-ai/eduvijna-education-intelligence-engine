# C01 Gate B candidate 2 — review response (B-F01..B-F05)

**Review base:** `1dfa543ad8696aede96581703d608276e033cf6c`  
**CI failure addressed:** Ruff UP017/E501 in `test_c01_migration_portability.py`

| ID | Fix |
| --- | --- |
| **B-F01** | Ruff fixes; `.eduvijna/pytest-targets.txt` includes C01 + D3 migration tests; `targeted-ci.yml` job `c01-migration-postgres` on PR synchronize; `postgresql+psycopg` driver; `EDUVIJNA_C01_DISPOSABLE_PG=1` opt-in |
| **B-F02** | SQLite `synthetic_test_only = 1` CHECK; PG `IS TRUE`; table `ACCESS EXCLUSIVE` lock before preflight; direct SQL tests for 0/2/-1 |
| **B-F03** | Raw `CAST(metadata_json AS TEXT)` / `::text` only; no reserialization fallback; nested non-finite walk; `audit_untrusted_legacy_flags()` read-only helper |
| **B-F04** | Real `source_revisions` DDL check; populated 0018→0021; downgrade/reupgrade; PG fresh with disposable guard |
| **B-F05** | Scope map v2; D3 tests in targeted pytest; C01-17 backup/restore **NOT_RUN** cand.2; overlay refresh partial |