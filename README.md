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
- Cursor implementation model, whenever Cursor is used: **Composer 2.5 Fast**.
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
