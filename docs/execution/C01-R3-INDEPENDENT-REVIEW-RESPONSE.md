# C01 Gate A candidate 3 — independent review response (R3-A01..A05)

**Review base SHA:** `30b1363663e6c9063a67683f4293fb90f7d3f34f` (pre-candidate-3 docs commit)  
**Delivery:** candidate 3 push on `closure/c01-foundation-database-recovery`  
**Harness reference run:** `c01_gatea_3528d62e02f2`

## R3-A01 — SQLite strict marker (CRITICAL)

| Issue | Resolution |
| --- | --- |
| Wrong predicate `json_type(json_extract(...))` inverted bool vs string | **Fixed** — `json_type(metadata_json, '$.d13_synthetic_test_only') = 'true'` with `json_valid` + root object guards |
| Report table vs transcript mismatch | **Corrected** in diagnostics + `*_sqlite_marker_matrix.log` (`bool-true` strict=1, `str-true` strict=0) |
| Duplicate JSON keys | **Preflight** `preflight_marker_eligible()` rejects duplicate `"d13_synthetic_test_only"` keys before any `::jsonb` cast; PG/SQLite strict SQL alone is **N/A** for dup rows (documented) |

## R3-A02 — `active_slot` CHECK verification (HIGH)

| Issue | Resolution |
| --- | --- |
| Five SELECT probes only | **Added** disposable table trials with NOT NULL `status`, `CHECK`, `UNIQUE(source_id, active_slot)` on PG and SQLite (`*_active_slot_constraints.log`) |
| Incomplete inventory | **Expanded** `C01-CHECK-CONSTRAINT-INVENTORY.md` — `0005`/`0006`/`source.py`/`day13_replay.py` |

## R3-A03 — Harness safety/reproducibility (HIGH)

| Issue | Resolution |
| --- | --- |
| `verify_baseline` incomplete | Ancestor check + migration tree blob + `backend/migrations`/`backend/app` diff vs baseline + dirty worktree fail-closed |
| Destructive drops / `set -e` | Owned `c01_gatea_*` DBs only; no pre-drop; `EXPECTED_FAILURE=100` for expected Alembic/SQL failures |
| Unconditional exit 0 on probes | Marker matrix + trials return nonzero on mismatch; main fails on unexpected exits |
| Provenance | Per-log `harness_sha256`, `repo_head`, `baseline_sha`, relative `log_path` |

## R3-A04 — Reconciliation/inventory (HIGH)

| Issue | Resolution |
| --- | --- |
| Overlay five keyed rows | Overlay builder retains keyed rows + prefix resolution for remaining 68; omissions `C01-OMIT-*` parent-linked |
| Scope map ranges | **27 explicit task rows** restored in `C01-GATE-A-SCOPE-MAP.md` |
| CI proof | **45574422240** cited separately from DB transcripts |

## R3-A05 — Decision packet (HIGH)

| Issue | Resolution |
| --- | --- |
| SQLite predicate correction | Documented in `C01-GATE-B-DECISION.md` |
| PG duplicate-key / NULL | Preflight abort-only; dup-key matrix shows cast collapse on PG |
| Unknown deployed state | Still **UNKNOWN**; sanitized evidence request unchanged |
| Gate B tests proposal | Fresh/populated both dialects, rollback, backup/restore, CI PG service — design only |

**Gate B:** still **LOCKED**. No fourth Gate A candidate.