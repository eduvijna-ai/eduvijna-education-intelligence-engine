# D03 — Founder Source Intelligence UAT

Day 4 remains locked during this acceptance.

## 1. Prepare and start

```bash
make env
make dev
```

Expected: backend and frontend become healthy.

## 2. Run Day-3 deterministic verification

In another terminal:

```bash
make source-verify
```

Expected JSON demonstrates:

- first synthetic official source revision reaches active;
- a changed revision is staged/extracted and diffed;
- pattern_drift_candidate is true;
- the first revision remains active before candidate approval;
- after approval/activation, the old revision is superseded;
- exactly one revision is active;
- source audit events were persisted.

## 3. Inspect CLI

```bash
make source-help
```

Expected commands include register, ingest-file, ingest-url, ingest-manual, extract, diff,
validate, approve, activate, reject, retry and inspect.

## 4. Run regression

```bash
make lint
make test
```

Expected:

- Ruff passes;
- Mypy passes;
- backend Pytest passes;
- frontend typecheck/build passes;
- migrations upgrade/downgrade/re-upgrade;
- Alembic reports no schema drift.

## 5. Private storage check

After a synthetic file ingestion, source bytes must exist beneath the configured
SOURCE_STORAGE_DIR and must not appear as tracked Git files.

## 6. Lifecycle acceptance

A source must follow:

```text
staged -> extracted -> diff -> validated -> approved -> active
```

Trying to activate before approval must fail.

Ingesting a changed revision must not alter the currently active checksum.

## 7. Security acceptance

Automated tests must prove:

- file:// and local/private URL targets are rejected;
- redirects to private targets are rejected;
- oversized responses are rejected;
- path traversal filenames are sanitized;
- backend credentials are not exposed to the frontend container.

## 8. Scope check

D03 must not include official CBSE/Telangana curriculum population, live AnythingLLM RAG,
LangGraph generation, public Source CRUD APIs or Day-4 work.

## Founder response

If accepted, provide an explicit Day-3 signoff. The system must then unlock only Day 4.
