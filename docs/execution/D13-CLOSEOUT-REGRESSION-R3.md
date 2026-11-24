# Day 13 closeout — Round 3 full historical regression (FINAL)

**Starting SHA (R3 handoff):** `2e61828248c5f8cbec241532ce1e68dff29cf8c2`  
**Raw log:** [D13-R3-FULL-REGRESSION-RAW.txt](./D13-R3-FULL-REGRESSION-RAW.txt)  
**Scoped CI mirror:** [D13-R3-SCOPED-VERIFICATION.txt](./D13-R3-SCOPED-VERIFICATION.txt)

> Full historical green on **local SQLite** with documented venv `PATH` is **engineering regression evidence only**. It does **not** upgrade the 36-task ledger, clear SOURCE_PENDING, pass Compose, prove live PostgreSQL/Alembic `20261124_0021`, or constitute Founder/D13-36 acceptance.

## Environment (recorded in raw log)

| Check | Value |
|---|---|
| `python --version` | Python 3.12.3 |
| `sys.executable` | `backend/.venv/bin/python` |
| `command -v alembic` | `backend/.venv/bin/alembic` |
| `python -m alembic --version` | alembic 1.20.1 |
| `PATH` prefix | `backend/.venv/bin` |

## Full suite invocation

```bash
cd backend
export PATH="$PWD/.venv/bin:$PATH"
set -o pipefail
python -m pytest tests/ -ra 2>&1 | tee ../docs/execution/D13-R3-FULL-REGRESSION-RAW.txt
```

## Result @ R3 execution (pre-push baseline SHA)

| Metric | Value |
|---|---|
| Collected / passed / failed / skipped | **2395 passed**, **0 failed**, **0 skipped** (2395 tests collected) |
| Warnings | 18 |
| Duration | 1834.80s (~30:35) |
| **pytest exit code** | **0** |
| Failed node IDs | *(none)* |

## Relation to R1/R2

| Round | Full `pytest tests/` | Notes |
|---|---|---|
| R1 | FAIL (8) | Default shell without venv `alembic` on `PATH` |
| R2 | NOT_RUN | Eight-test attribution only — see [D13-CLOSEOUT-REGRESSION-R2.md](./D13-CLOSEOUT-REGRESSION-R2.md) |
| **R3** | **PASS (2395)** | Single run with `PATH="$PWD/.venv/bin:$PATH"`; same eight migration tests included |

## Limits (unchanged)

- SQLite dev database only; no production DB or secrets.
- Live PostgreSQL migrate for `20261124_0019–0021` **NOT_RUN** (`json_extract` portability on 0021 documented — no closeout patch).
- Targeted CI ≠ historical suite; Draft **compose-smoke** remains **SKIPPED**, not PASS.