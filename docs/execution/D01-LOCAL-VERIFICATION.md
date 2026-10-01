# D01 local verification evidence

Performed before GitHub PR handoff on 2026-10-01.

## Backend

- pytest: 8 passed
- Python compile validation: passed
- SQLite connection smoke: passed

## Migration round-trip

Using a fresh SQLite database:

1. alembic upgrade head — passed
2. alembic downgrade -1 — passed
3. alembic upgrade head — passed
4. system_settings table present after final upgrade

## External-version checks used for foundation

- MCP Python SDK: v2 stable line; Day-1 uses MCPServer rather than the removed v1 FastMCP import.
- React: current stable 19.3 line.
- Vite: current stable 8.3 line.

GitHub Actions remains the authoritative deterministic check for ruff, mypy, installed MCP import, frontend dependency resolution/typecheck/build, and migration execution in the repository environment.
