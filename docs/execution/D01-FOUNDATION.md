# D01 — Foundation

Status: **ACTIVE**

Founder approval: **NOT GRANTED**

Next day: **D02 LOCKED**

## Objective

Deliver a clean local engineering foundation where React + FastAPI + SQLite + migrations + tests + Docker Compose run reliably, while PostgreSQL compatibility, AI/RAG boundaries, MCP boundaries, tenant context, observability foundations, and Kubernetes-readiness are established without implementing education-domain features yet.

Day 1 is complete only when every Definition-of-Done item is green and the Founder accepts the localhost smoke test.

## Cost rule

All work must fit inside the existing subscription budget.

- Cursor implementation model: **Composer 2.5 Fast** *(historical Day 1 record; superseded for current work by Founder 2026-10-05 standard **Composer 2.5** requirement — see `AGENTS.md`)*
- ChatGPT Pro: existing USD 100 plan only
- Cursor Pro+: existing USD 60 plan only
- No planned paid overage
- No paid GitHub runners
- No Codespaces
- No duplicate full-builder agents

If included quota is exhausted, report a blocker. Do not enable additional paid usage.

## Technology baseline

Backend:

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy 2.x
- Alembic
- httpx
- pytest
- ruff
- mypy

Frontend:

- React
- TypeScript
- Vite

Databases:

- LOCAL: SQLite
- PRODUCTION: PostgreSQL through the same SQLAlchemy/application boundary

## Required repository structure

Create the practical Day-1 skeleton for:

```text
backend/
  app/
    api/
    core/
    db/
    models/
    schemas/
    repositories/
    services/
    engines/
      curriculum/
      examination/
      question/
      diagnostic/
      learner/
      knowledge/
    adapters/
      ai/
      rag/
      memory/
      storage/
      anythingllm/
    agents/
    graphs/
    nodes/
    jobs/
    mcp/
  tests/
  migrations/

frontend/
  src/
    api/
    components/
    features/
      curriculum/
      exams/
      questions/
      diagnostics/
      learners/
      knowledge/
      admin/
    layouts/
    pages/
    routes/
    hooks/
    types/
    utils/

content/
  curricula/
  exams/
  taxonomies/
  rubrics/

scripts/
  ingestion/
  maintenance/

infra/
  docker/
  kubernetes/

.github/
  workflows/
```

Do not create empty files only to imitate structure where they add no value. Use package placeholders only where tooling requires them.

## Backend foundation

Required endpoints:

- `GET /health`
- `GET /ready`
- `GET /api/v1/system/info`

Expected health semantics:

- `/health`: process is alive.
- `/ready`: application initialized and database reachable.
- AnythingLLM must not be required for Day-1 readiness.

All public product APIs start under `/api/v1/`.

## Configuration

Provide typed environment-driven settings.

Minimum variables:

```text
APP_ENV=local
DATABASE_URL=sqlite:///./data/eduvijna.db
ANYTHINGLLM_BASE_URL=
ANYTHINGLLM_API_KEY=
API_SECRET_KEY=
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173
```

Commit `.env.example` and `.env.development.example`; never commit `.env` or `.env.development`. The Founder-editable local runtime file is `.env.development`, and process environment variables must override file values.

No business code may branch on production merely to decide SQL behavior.

## Database abstraction

Configure SQLAlchemy so local SQLite can later switch to PostgreSQL without rewriting domain models/services.

Create the minimum infrastructure for:

- declarative Base;
- session management;
- repository boundary;
- unit-of-work boundary or equivalent transaction boundary.

Only a minimal smoke persistence model is necessary on Day 1. Do not prematurely implement the complete curriculum/exam schema.

## Alembic

Required:

- upgrade from a fresh database;
- downgrade at least one revision;
- upgrade again successfully.

If rollback is broken, Day 1 fails.

## Frontend foundation

Create React + TypeScript + Vite.

The home page must visibly identify:

- Eduvijna
- Education Intelligence Engine
- current environment
- backend connection status obtained from the backend, not hard-coded.

The frontend must call `GET /api/v1/system/info`.

## Docker Compose

One command must start the local base application:

```bash
docker compose up --build
```

It must start at least:

- backend
- frontend

AnythingLLM may be an optional profile and must not block Day-1 base startup.

Expected local surfaces:

- frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

## AnythingLLM boundary

Do not deeply integrate RAG on Day 1.

Create interfaces/adapters so application services do not scatter AnythingLLM HTTP calls.

Minimum conceptual capabilities:

- health
- generate
- retrieve
- embed

Concrete AnythingLLM code belongs behind a dedicated adapter boundary.

## Agent boundary

Create framework-neutral run/state/result concepts and reserve LangGraph integration boundaries.

Business logic must remain callable and testable without LangGraph.

## MCP boundary

Install/pin the intended MCP Python SDK and create a minimal MCP server foundation.

Day-1 acceptance is only that the MCP server foundation boots / exposes a trivial health-like capability where practical.

No educational generation tools are required yet.

## Logging and request IDs

Every API request should support structured metadata including:

- request_id
- timestamp
- path
- method
- status
- duration

Never log secrets or full auth tokens.

## Error contract

Use one stable API error envelope such as:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "...",
    "request_id": "..."
  }
}
```

## Tenant context foundation

Introduce placeholders/concepts for:

- organization_id
- institution_id
- actor_id

Full authentication is not a Day-1 requirement. The architecture must simply avoid becoming single-tenant by accident.

## Audit and usage boundaries

Provide basic interfaces/schemas for future audit events and AI usage accounting.

Future usage dimensions include request/run identifiers, model, latency, input/output usage where returned, and generation purpose.

No dashboard required on Day 1.

## Kubernetes-readiness constraints

Containers should be designed for later DOKS deployment:

- environment configuration;
- stateless API filesystem assumptions;
- health endpoint;
- readiness endpoint;
- graceful shutdown;
- non-root container where practical.

No Kubernetes deployment is required on Day 1.

## Tests

Backend minimum:

- health endpoint;
- readiness endpoint;
- system info endpoint;
- SQLite connection/persistence;
- configuration parsing;
- invalid configuration behavior;
- standard error envelope;
- Alembic migration smoke test.

Frontend minimum:

- typecheck;
- production build;
- basic backend integration behavior.

## CI

GitHub Actions on pull requests must run using standard public-repository runners.

Backend:

- ruff
- mypy
- pytest

Frontend:

- install
- typecheck
- build

Migration:

- upgrade a fresh SQLite database

Do not configure paid runners.

## Developer commands

Provide a simple Makefile/task interface equivalent to:

```bash
make setup
make dev
make test
make lint
make migrate
make migration
make down
```

Exact commands may vary if the replacement is simpler and documented.

## Founder localhost acceptance

The Founder should be able to perform:

1. Run `docker compose up --build`.
2. Open `http://localhost:5173` and see Eduvijna plus live backend connectivity.
3. Open `http://localhost:8000/health` and receive healthy status.
4. Open `http://localhost:8000/docs` and see FastAPI OpenAPI.
5. Stop and restart the app and confirm SQLite-backed state persists.
6. Run the documented test command and see the Day-1 suite pass.

## Definition of Done

Day 1 is not ready for Founder review until all are true:

- [ ] repository structure is established;
- [ ] backend runs;
- [ ] frontend runs;
- [ ] frontend talks to backend;
- [ ] SQLite works;
- [ ] PostgreSQL-compatible abstraction exists;
- [ ] Alembic upgrade works;
- [ ] Alembic rollback works;
- [ ] Docker Compose works;
- [ ] configuration is environment-driven;
- [ ] AnythingLLM adapter boundary exists;
- [ ] agent/LangGraph boundary exists;
- [ ] MCP foundation boots;
- [ ] request IDs and structured logging work;
- [ ] standard error contract works;
- [ ] tenant-context foundation exists;
- [ ] audit foundation exists;
- [ ] usage/cost instrumentation boundary exists;
- [ ] public API versioning exists;
- [ ] backend tests pass;
- [ ] frontend typecheck/build passes;
- [ ] CI passes;
- [ ] no secret is committed;
- [ ] Founder localhost smoke test instructions are accurate;
- [ ] no Day-2 implementation has started.

When this list is green, stop and request Founder acceptance.

**Do not start D02.**
