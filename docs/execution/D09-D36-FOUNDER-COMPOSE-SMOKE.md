# D9-36 — Founder localhost Docker Compose smoke

**Cursor status:** `BLOCKED_DOCKER_UNAVAILABLE` (Cloud Agent VM has no `docker` binary).

**Do not treat skipped targeted-CI `compose-smoke` (Draft PR) or this blocker as PASS.**

## Prerequisites

- Docker Engine + Compose v2
- Git checkout at the SHA you intend to smoke-test (`git rev-parse HEAD`)
- Synthetic credentials only (no real AnythingLLM keys or private curriculum)
- **Shell:** POSIX `sh` for the pytest target stanza below; Bash is fine for other steps

**Image layout:** `backend/Dockerfile` copies `backend/tests` → `/app/tests` and `.eduvijna/execution-state.yml` only. It does **not** copy `.git`, `git`, or `.eduvijna/pytest-targets.txt`. Paths in `.eduvijna/pytest-targets.txt` are relative to `backend/` (e.g. `tests/test_day9_diagnostic.py`) and match `/app/tests/...` inside the container.

## A — Host: exact-SHA Founder verifiers (optional but recommended)

Run on the **host** where the repository `.git` directory exists (same evidence model as targeted PR CI). **Do not** run `day8_verify` / `day9_verify` inside the backend container expecting `candidate_sha_matches_head` to pass — `_git_head()` is `"unknown"` without `.git`.

```bash
# From repository root; backend venv with dev deps installed
export EDUVIJNA_CANDIDATE_SHA="$(git rev-parse HEAD)"
cd backend
python -m app.day8_verify
python -m app.day9_verify --json
```

**Expected:** `day8_verify` OK; `day9_verify` JSON `"ok": true` and `"candidate_sha_matches_head": true`.

## B — Container: Compose stack smoke (required for D9-36 Compose gate)

All commands below assume **repository root** as the current working directory.

### Setup (matches `.github/workflows/ci.yml` `compose-smoke`)

```bash
cp .env.development.example .env.development
printf '\nANYTHINGLLM_BASE_URL=http://anythingllm.example\nANYTHINGLLM_API_KEY=ci-dummy-anything-key\nMCP_API_KEY=ci-dummy-mcp-key\n' >> .env.development

docker compose --env-file .env.development config
docker compose --env-file .env.development up --build -d
```

### Health and routes

```bash
# Wait until ready (repeat up to ~60s)
curl --fail --silent http://127.0.0.1:8000/ready
curl --fail --silent http://127.0.0.1:8000/health
curl --fail --silent http://127.0.0.1:8000/api/v1/system/info
curl --fail --silent http://127.0.0.1:5173/ >/dev/null
```

**Expected:** HTTP 200 on all; JSON from `/api/v1/system/info` without secrets.

### Focused Day 7/8/9 pytest inside backend container

Resolve targets on the **host** from `.eduvijna/pytest-targets.txt` (same pattern as `.github/workflows/targeted-ci.yml`), then pass them to a one-off `run --rm` backend container (working directory `/app`):

```sh
set -- $(grep -Ev '^[[:space:]]*(#|$)' .eduvijna/pytest-targets.txt)
test "$#" -gt 0 || { echo 'No pytest targets configured.'; exit 1; }
docker compose --env-file .env.development run --rm backend pytest -q "$@"
```

**Expected:** pytest exit code 0. Each argument is a path like `tests/test_day9_diagnostic.py`, valid under `/app/tests/` in the image.

### SQLite persistence across restart (from `ci.yml`)

```bash
docker compose exec -T backend python - <<'PY'
from app.db.session import session_factory
from app.models import SystemSetting
session = session_factory()()
try:
    row = session.query(SystemSetting).filter_by(key="ci.persistence").one_or_none()
    if row is None:
        session.add(SystemSetting(key="ci.persistence", value="survives-restart"))
    else:
        row.value = "survives-restart"
    session.commit()
finally:
    session.close()
PY

docker compose --env-file .env.development down
docker compose --env-file .env.development up -d
# wait for /ready, then:
curl --fail --silent http://127.0.0.1:8000/ready
docker compose exec -T backend python - <<'PY'
from app.db.session import session_factory
from app.models import SystemSetting
session = session_factory()()
try:
    assert session.query(SystemSetting).filter_by(key="ci.persistence").one().value == "survives-restart"
finally:
    session.close()
PY
```

### Cleanup

```bash
docker compose --env-file .env.development down
```

## Evidence to return to PR #27

- `git rev-parse HEAD` tested
- **Section A:** host verifier pass/fail (if run)
- **Section B:** config/up, each curl, container pytest exit code, persistence assert, teardown
- Sanitized health/status lines only — **no** real API keys, env dumps, or private source text
