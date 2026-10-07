# Eduvijna Education Intelligence Engine

Eduvijna is an education intelligence platform spanning:

- Curriculum Intelligence
- Examination Intelligence
- Knowledge Intelligence
- Question Intelligence
- Diagnostic Intelligence
- Learner Intelligence

## v1.0 execution model

- Kickoff: 2026-10-01
- Source of truth: this GitHub repository.
- Primary implementation mode: zero-overage connected implementation.
- Cursor implementation model, whenever Cursor is used: **Composer 2.5** (standard; not Composer 2.5 Fast). Governing dated override: explicit Founder message 2026-10-05, reconfirmed 2026-10-06 — see `AGENTS.md` and `.eduvijna/execution-state.yml`.
- Cursor Cloud Agent usage-based/on-demand billing: **disabled by project budget policy**.
- Independent review: Codex.
- Deterministic verification: GitHub Actions.
- Founder approval is required at the end of every development day.
- The next development day remains locked until the previous day is Founder-approved.

## Budget guardrail

The v1.0 implementation must fit inside the existing monthly subscriptions:

- ChatGPT Pro: USD 100
- Cursor Pro+: USD 60
- GitHub public repository / standard GitHub-hosted Actions: no planned paid usage
- Planned tooling ceiling: **USD 160/month**
- Do not intentionally enable usage-based overages, paid runners, Codespaces, or duplicate full implementation agents.

## Data and infrastructure boundaries

- Local database: SQLite
- Production database: PostgreSQL
- AI/RAG gateway: AnythingLLM adapter boundary
- Deployment target: DigitalOcean Kubernetes
- Public API namespace: `/api/v1`

Read `AGENTS.md` and the active specification under `docs/execution/` before changing code.


## Local development environment

Create the Founder-editable local environment file once:

```bash
make env
```

This copies `.env.development.example` to the Git-ignored `.env.development`.
Add your own integration values there; do not commit the real file.

Supported placeholders currently include:

```text
ANYTHINGLLM_BASE_URL=
ANYTHINGLLM_API_KEY=
API_SECRET_KEY=
MCP_API_KEY=
```

Native Pydantic settings and the documented Docker Compose commands consume the development
file. Real process environment variables take precedence over file values. Docker keeps its
container-specific SQLite path while receiving Founder-supplied API/AnythingLLM/MCP credentials
only in the backend container. The frontend container receives only VITE_API_BASE_URL.

Then start the stack with:

```bash
make dev
```

Day 3 Source Intelligence is the active development scope. Day 4 remains locked until Day 3 receives explicit Founder approval.

Source documents are stored under the configured private runtime storage path (default
`./data/private/sources`), which is excluded from Git. Engineering verification commands:

```bash
make source-verify
make source-help
```

