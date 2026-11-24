# D13-INTEGRATION-01 — Compose smoke repair evidence

**Starting HEAD:** `1dc425d8c2d34ee3300e87a56c8ca7578eb1d97f`  
**Failure reference:** [Targeted CI run 45374189883](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/actions/runs/45374189883), job `compose-smoke` (three pytest failures).

## Root cause

| Failure | Cause |
|---|---|
| `test_d13_scope_map_has_36_rows` | `D13-SCOPE-MAP.md` not copied into backend image (`backend/Dockerfile` had D12 map only). |
| `test_day13_verify_fails_on_sha_mismatch` | Verifier crashed (missing scope file) → empty stdout / JSONDecodeError. |
| `test_day13_verify_passes_with_aligned_sha` | Container has no `.git`; verifier required `git rev-parse` for observed revision. |

## Repair (minimal)

1. **Dockerfile:** `COPY docs/execution/D13-SCOPE-MAP.md`; bake `EDUVIJNA_BUILD_REVISION` build-arg into read-only `/app/.eduvijna/build-revision` (40-hex SHA).
2. **`app/verification/candidate_revision.py`:** Fail-closed SHA evidence — prefer Git when present; else immutable build metadata; reject conflict, malformed, or missing observed revision.
3. **`day13_verify`:** Use shared revision evidence; emit structured JSON on exceptions (no silent crash).
4. **`docker-compose.yml`:** Pass `EDUVIJNA_BUILD_REVISION` build arg.
5. **`targeted-ci.yml` `compose-smoke`:** Detach-checkout exact `EDUVIJNA_CANDIDATE_SHA`, verify `git rev-parse`, inject build revision into `.env.development` before `docker compose build`.
6. **Tests:** `test_candidate_revision.py`, updated `test_day13_verify_sha.py`.

## Local verification

| Check | Result |
|---|---|
| Ruff / Mypy | PASS |
| `pytest` `test_day13_m0_governance.py` `test_day13_verify_sha.py` `test_candidate_revision.py` | **11 passed** |
| `day13_verify --json` (host, aligned SHA) | PASS, `sha_alignment: true` |
| Docker Compose reproduction | **NOT_RUN** (docker CLI absent on agent VM) |

## Post-push CI

Record exact run URL and job conclusions on PR handback (`backend-targeted` + `compose-smoke` required SUCCESS).

## Governance (unchanged)

Ledger **0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED**; D13-36 pending; F03-A/F03-B/F04-A/D13-31A STOP; Day11 hold; Day14 LOCKED; no source approval or merge.