# D9-36 — Founder localhost Docker Compose smoke

**Cursor status:** `BLOCKED_DOCKER_UNAVAILABLE` (Cloud Agent VM has no `docker` binary).

**Do not treat skipped targeted-CI `compose-smoke` (Draft PR) or this blocker as PASS.** Founder may run the checklist below locally or authorize full `ci.yml` on a non-draft revision.

## Prerequisites

- Docker Engine + Compose v2
- Repository at acceptance SHA (current docs HEAD: `6f85faeb0690c1720e4d60e0a032733246204ce8`, or frozen code SHA: `eede5d67048502211d867ba45390b43c4f820f1d`)
- Synthetic credentials only (no real AnythingLLM keys or private curriculum)

## Setup (matches `.github/workflows/ci.yml` `compose-smoke`)

```bash
git checkout <acceptance-sha>
cp .env.development.example .env.development
printf '\nANYTHINGLLM_BASE_URL=http://anythingllm.example\nANYTHINGLLM_API_KEY=ci-dummy-anything-key\nMCP_API_KEY=ci-dummy-mcp-key\n' >> .env.development

docker compose --env-file .env.development config
docker compose --env-file .env.development up --build -d
```

## Health and routes

```bash
# Wait until ready (repeat up to ~60s)
curl --fail --silent http://127.0.0.1:8000/ready
curl --fail --silent http://127.0.0.1:8000/health
curl --fail --silent http://127.0.0.1:8000/api/v1/system/info
curl --fail --silent http://127.0.0.1:5173/ >/dev/null
```

**Expected:** HTTP 200 on all; JSON from `/api/v1/system/info` without secrets.

## Day 8 / Day 9 verifiers and focused tests (container)

Align with D9-36 acceptance; extend CI compose job with Day 8/9 harnesses:

```bash
export EDUVIJNA_CANDIDATE_SHA=<acceptance-sha>

docker compose exec -T backend python -m app.day8_verify
docker compose exec -T backend python -m app.day9_verify --json

# Targeted Day 9 + Day 7/8 boundary suite (same as targeted CI)
docker compose exec -T -e EDUVIJNA_CANDIDATE_SHA backend bash -lc '
  mapfile -t targets < <(grep -Ev "^\s*(#|$)" .eduvijna/pytest-targets.txt)
  pytest -q "${targets[@]}"
'
```

**Expected:** `day8_verify` / `day9_verify` OK; pytest exit 0.

## SQLite persistence across restart (from `ci.yml`)

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

## Cleanup

```bash
docker compose --env-file .env.development down
```

## Evidence to return to PR #27

- Exact `git rev-parse HEAD` tested
- Pass/fail per step (config, up, curls, verifiers, pytest, persistence)
- Sanitized `docker compose ps` or health curl status lines only
- **No** real API keys, env dumps, or private source text
