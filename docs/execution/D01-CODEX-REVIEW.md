# D01 Codex review record

Independent Codex review of commit `52a2bc7` identified four P1 findings:

1. Backend development/test container did not include `tests/`.
2. Alembic configuration did not escape percent-encoded PostgreSQL URLs.
3. HTTP/framework and unexpected errors were not consistently wrapped in the public error envelope.
4. The local default API secret could be accepted outside local mode.

All four findings are addressed in commit `8d4d617`.

Regression coverage was added for:
- non-local secret rejection;
- percent-encoded PostgreSQL URL preservation;
- 404 error envelope;
- sanitized unexpected 500 envelope.

The backend test image now contains tests, and Compose CI runs the documented `make lint` and `make test` commands.

The MCP v2 server also has a guarded direct execution entry point using `mcp.run()`.
