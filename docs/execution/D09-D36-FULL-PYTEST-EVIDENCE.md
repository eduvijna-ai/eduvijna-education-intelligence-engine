# D9-36 — full historical pytest evidence

## Current frozen code SHA run (`e1608dd…`)

This is the **authoritative** full-suite run for Day 9 specification-closure acceptance candidate **`e1608dd60eb0604b2d68d307e2a7e90db4afbbec`**. The prior `eede5d6…` run does **not** certify this tree.

### Execution record

| Field | Value |
|-------|--------|
| `git rev-parse HEAD` at run | `e1608dd60eb0604b2d68d307e2a7e90db4afbbec` |
| `EDUVIJNA_CANDIDATE_SHA` | `e1608dd60eb0604b2d68d307e2a7e90db4afbbec` |
| Runner | Cursor Cloud Agent VM (`linux`, workspace `/workspace`) |
| Python | 3.12.3 (`backend/.venv`) |
| Command | `cd backend && python -m pytest tests --tb=short -ra` |
| Started (UTC) | 2026-10-19T12:04:50Z |
| Ended (UTC) | 2026-10-19T12:40:05Z |
| Duration | 2115 s wall (~35.2 min) |
| Shell exit code | **0** |

### Summary counts (pytest footer)

| Metric | Value |
|--------|--------|
| **Passed** | **1839** |
| Failed | 0 |
| Skipped | 0 (none reported) |
| XFailed / XPassed | 0 (none reported) |
| Warnings | 11 |

Footer line: `1839 passed, 11 warnings in 2111.34s (0:35:11)`

### Warnings (sanitized)

- `LangChainPendingDeprecationWarning` — LangGraph checkpoint `allowed_objects` default.
- `DeprecationWarning` — Alembic `path_separator` in migration subprocess tests (Day 3/4 migration tests).

### Log artifact

Sanitized full log: `/opt/cursor/artifacts/d9-36-full-pytest-e1608dd.log` (Cursor agent upload; not committed to Git).

---

## Superseded run (`eede5d6…`) — historical only

| Field | Value |
|-------|--------|
| SHA | `eede5d67048502211d867ba45390b43c4f820f1d` |
| Command | `pytest tests -q --tb=no` |
| Collected | 1784 (collect-only) |
| Passed/skipped/xfail | **UNVERIFIED** (`-q` omitted footer) |
| Exit | 0 |

Do not substitute this run for acceptance of `e1608dd…` application code.
