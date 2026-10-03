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

If two candidates were reviewed against the same active revision, activating one makes the other
candidate stale. The stale candidate must fail activation until it receives a fresh diff against
the new active revision, is validated again and is approved again.

## 7. Security acceptance

Automated tests must prove:

- file:// and local/private URL targets are rejected;
- redirects to private targets are rejected;
- the actual connected peer is checked against private/non-public addresses;
- oversized responses are rejected;
- path traversal filenames are sanitized;
- backend credentials are not exposed to the frontend container.

## 8. Scope check

D03 must not include official CBSE/Telangana curriculum population, live AnythingLLM RAG,
LangGraph generation, public Source CRUD APIs or Day-4 work.

## Founder response

If accepted, provide an explicit Day-3 signoff. The system must then unlock only Day 4.


## Rework closure verification

The automated Day-3 regression additionally verifies:

- prohibited/private URL targets are rejected before a real request is sent;
- concurrent identical uploads do not delete the successful stored object;
- concurrent different uploads receive distinct revision numbers;
- withdrawing approval in another session prevents stale activation;
- active status and active slot cannot disagree;
- source bytes cannot be substituted before extraction or changed after approval;
- manual metadata checksum/size is recomputed during validation;
- institution/teacher source ownership and internal access scopes are enforced;
- MIME/method/filename conflicts, malformed CSV and non-standard JSON constants are rejected;
- missing storage produces a failed state and identical re-ingestion restores it safely;
- synthetic tokens are absent from configured logs;
- same source bytes plus material metadata changes create a reviewable candidate revision;
- deliberately failed SQLite migrations leave the previous schema/revision intact and can be retried.

Founder does not need to reproduce the concurrency and migration-failure injections manually.
A green exact-commit CI run is the deterministic evidence for those cases.
