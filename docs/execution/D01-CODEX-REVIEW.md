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


## Second Codex pass

Codex re-reviewed commit `9f7f2ea` and identified three further Day-1 acceptance gaps:

1. The checked-in `.env.example` contained a second repository-known placeholder secret.
2. Structured request logs omitted the required UTC timestamp.
3. Persistence tests did not yet prove a committed SQLite row survived database/container reopening.

These are addressed in commit `2810037`.

Additional regression coverage now verifies:
- every shipped API-secret placeholder is rejected outside local mode;
- structured request events contain an offset-aware UTC timestamp;
- SQLite data survives engine disposal/reopen;
- Compose writes a real `SystemSetting`, restarts the stack without deleting the volume, and reads the value back afterward.
