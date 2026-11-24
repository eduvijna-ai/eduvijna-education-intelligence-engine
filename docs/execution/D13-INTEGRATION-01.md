# D13-INTEGRATION-01 — Compose smoke + revision evidence hardening

**Baseline HEAD (INT-R):** `ddb1058d99d7d35f11ecd4be44da8e29d24c4db9`  
**Architect gate:** [PR comment 7129427408](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/53#issuecomment-7129427408)  
**Prior integration:** [PR comment 7128922501](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/pull/53#issuecomment-7128922501)

## Round 1 — scope map + Compose (summary)

| Failure | Fix |
|---|---|
| Missing `D13-SCOPE-MAP.md` in image | `COPY` in `backend/Dockerfile` |
| Verifier crash on mismatch / missing scope | Structured JSON + scope ledger on failure paths |
| No Git in container | Image build revision metadata + exact PR HEAD pin in CI |

Initial green: targeted CI with `compose-smoke` SUCCESS (pre-hardening tip `ddb1058`).

## Round 2 — INT-R01..R03 (final hardening)

### INT-R01 — trusted independent image revision

- Fixed metadata path: **`/etc/eduvijna/build-revision`** (root-owned dir `0555`, file `0444`, **not** under writable `/app`).
- **Removed** runtime overrides (`EDUVIJNA_BUILD_REVISION_PATH`, execution-state-derived paths).
- Build-arg `EDUVIJNA_BUILD_REVISION` validated (40-hex) at image build; derived from **independently checked-out PR HEAD** in CI before `docker compose build` — never from runtime `EDUVIJNA_CANDIDATE_SHA` alone.
- Trust boundary: alignment is **not** cryptographic attestation against a privileged builder; it binds expected candidate SHA to immutable image metadata + optional host Git when both exist (conflict → fail).

### INT-R02 — strict fail-closed verification

- Distinguishes **absent** vs **invalid/unreadable/non-UTF8** image metadata; present-invalid fails even when Git is valid.
- Malformed `EDUVIJNA_CANDIDATE_SHA` → `revision_evidence_error`.
- `day13_verify` resolves revision **once** in `main()`; exception path does not re-probe metadata.
- Scope-map ledger still required on synthetic path; no fabricated counts.

### INT-R03 — tests + CI coverage

- `tests/test_candidate_revision.py` added to `.eduvijna/pytest-targets.txt`.
- Unit tests use **injection only** (`git_sha_override`, `image_revision_path`); git/no-git paths covered without requiring `git` in unit tests.
- `test_protected_image_revision_not_tamperable_by_runtime_user` runs in real Compose (non-root).
- `test_day13_verify_passes_with_aligned_sha` requires `observed_source` ∈ `{git, build_revision}` and `sha_alignment: true`.

### Local verification (agent VM)

| Check | Result |
|---|---|
| Ruff | PASS |
| Mypy (362 files) | PASS |
| `pytest` `test_candidate_revision.py` + `test_day13_verify_sha.py` | **13 passed**, 1 skipped (tamper test — no image metadata on host) |
| `day13_verify --json` (host Git aligned) | `ok: true`, `sha_alignment: true` |
| Docker Compose | **NOT_RUN** (no docker CLI) |

### INT-R test names (adversarial + positive)

`test_image_revision_malformed_present`, `test_image_revision_non_utf8_fails_even_with_valid_git`, `test_revision_conflict_without_git_cli`, `test_build_revision_alignment_without_git`, `test_no_observed_evidence_fails_closed`, `test_malformed_candidate_sha`, `test_resolve_unknown_evidence_unit`, `test_protected_image_revision_not_tamperable_by_runtime_user` (Compose), `test_day13_verify_passes_with_aligned_sha`, `test_day13_verify_fails_on_sha_mismatch`

### Post-push CI

Record exact-tip `backend-targeted` + **`compose-smoke`** conclusions on PR handback.

## Governance (unchanged)

Ledger **0 PASS / 33 PARTIAL / 2 SOURCE_PENDING / 1 NOT_STARTED**; D13-36 pending; F03-A/F03-B/F04-A/D13-31A STOP; Day11 hold; Day14 LOCKED; no merge.