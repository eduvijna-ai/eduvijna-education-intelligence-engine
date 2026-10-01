# D01 Founder Localhost Acceptance

Do not approve D01 until these checks pass.

1. Run `docker compose up --build`.
2. Open `http://localhost:5173`.
   - Expect **Eduvijna — Education Intelligence Engine**.
   - Expect **Backend: Connected**.
   - Expect **Environment: local**.
3. Open `http://localhost:8000/health`.
   - Expect `{"status":"ok"}`.
4. Open `http://localhost:8000/ready`.
   - Expect `{"status":"ready"}`.
5. Open `http://localhost:8000/docs`.
   - Expect FastAPI OpenAPI UI.
6. Run `make test`.
   - Expect backend tests, frontend typecheck/build, and migration round-trip to succeed.
7. Persistence:
   - Stop the stack with `docker compose down` (do not add `-v`).
   - Start it again.
   - `/ready` must still succeed and the named `eduvijna_sqlite` volume must still exist.
8. Verify no D02 feature work is present.

If all checks pass, Founder response should be: `APPROVE DAY 1`.
If a check fails, reply with `REJECT DAY 1` plus the failing step and observed result.
