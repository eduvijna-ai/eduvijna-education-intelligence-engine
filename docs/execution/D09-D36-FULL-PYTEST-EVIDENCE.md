# D9-36 — full historical pytest evidence (one-time run)

Metadata for the single D9-36 full-suite run. **No second full regression** unless Founder authorizes.

## Execution record

| Field | Value |
|-------|--------|
| `git rev-parse HEAD` at run | `eede5d67048502211d867ba45390b43c4f820f1d` |
| `EDUVIJNA_CANDIDATE_SHA` | `eede5d67048502211d867ba45390b43c4f820f1d` |
| Runner | Cursor Cloud Agent VM (`linux`, workspace `/workspace`) |
| Python | 3.12 (`backend/.venv`) |
| Command | `cd backend && python -m pytest tests -q --tb=no` |
| Started (UTC) | 2026-10-15T11:51:58Z (shell session metadata) |
| Ended (UTC) | 2026-10-15T12:20:13Z |
| Duration | ~28.3 min (1,695,362 ms wall time) |
| Shell exit code | **0** |

## Counts

| Metric | Value | Verification |
|--------|--------|----------------|
| Collected (pre-run `pytest tests --collect-only`) | **1784** | Verified via separate collect-only on same tree |
| Failed | **0** | Inferred from exit 0 + 100% progress dots; no failure output in log |
| Passed | **UNVERIFIED** | Pytest `-q` with zero failures did not emit a `N passed` summary line |
| Skipped | **UNVERIFIED** | Not printed under `-q` |
| XFailed / XPassed | **UNVERIFIED** | Not printed under `-q` |

**Evidence limitation:** The preserved log contains progress percentage lines and warnings only (see excerpt below). For auditor-visible `passed/skipped/xfail` footer counts, either accept this metadata + exit code, or Founder authorizes one re-run with `pytest tests --tb=no -q` replaced by `pytest tests --tb=no` (non-quiet) or `-rA` on the frozen code SHA.

## Warnings (sanitized summary)

- `LangChainPendingDeprecationWarning` — LangGraph checkpoint `allowed_objects` default (1×).
- `DeprecationWarning` — Alembic `path_separator` in migration subprocess tests (10× across Day 3/4 migration tests).

No test failures or errors appear in the log.

## Sanitized log excerpt (tail)

```
........................................................................ [ 96%]
........................................................                 [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/langgraph/checkpoint/base/__init__.py:18
  LangChainPendingDeprecationWarning: The default value of `allowed_objects` will change ...

tests/test_day3_final_compatibility.py: 2 warnings
tests/test_day3_rework_migration.py: 2 warnings
tests/test_day4_successor_migration.py: 5 warnings
tests/test_source_intelligence_migration.py: 1 warning
  DeprecationWarning: No path_separator found in configuration; ... Alembic config.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
```

Full progress log (38 lines, dots only): recoverable on Cursor agent artifact path `d9-36-full-pytest.log` when the same VM/session is retained; **not** uploaded to GitHub prior to this document.
