# D03 — Audited Rework Closure

Status: **ENGINEERING COMPLETE / FOUNDER REVIEW**

Day 4: **LOCKED**

This report closes only the Founder-approved Day-3 audit rework D3-R01 through D3-R10.
It does not start Day 4 and does not infer Founder acceptance.

| Rework | Closure |
|---|---|
| **D3-R01 — pre-send SSRF** | Real URL retrieval now resolves and validates global IPs before connecting, pins the socket to the validated IP, retains the original hostname for TLS/Host, validates each redirect before its next request, rejects non-global ranges, and keeps mock transport support for CI. Tests prove a prohibited resolver result does not invoke the connection factory. |
| **D3-R02 — concurrent upload/storage loss** | Runtime source files are content-addressed by SHA-256. Atomic publish is race-safe, failed DB contenders never delete a successful object, and revision allocation retries on uniqueness/SQLite-lock conflicts. Two-session tests cover same-content and different-content races. |
| **D3-R03 — stale approval / active invariant** | Revision reads used for approval/activation refresh database state and use locking where supported. A second-session rejection prevents stale activation. The database constraint now requires active status iff active_slot=1; invalid combinations fail. |
| **D3-R04 — migration failure atomicity** | SQLite migration execution uses one explicit transaction for DDL plus alembic_version update, performs foreign_key_check before commit, rolls back schema/version on failure, then restores FK enforcement. Tests cover partial-schema collision and FK-validation failure, followed by successful retry. |
| **D3-R05 — evidence/content binding** | Extraction verifies stored bytes before parsing and records extracted checksum. Validation recomputes bytes/manual metadata checksum, verifies snapshot and extraction binding, and records validated checksum. Approval stores a fingerprint over the exact evidence/diff baseline. Activation refreshes state and rechecks bytes, snapshot, diff and approval fingerprint before changing active state. |
| **D3-R06 — ownership/scoped provenance** | Source supports organization/institution/teacher ownership with DB relationship constraints and source-type ownership shape. Internal service scope enforces organization/institution/teacher boundaries for reads, ingestion and provenance operations. Tests cover valid ownership and cross-scope rejection. |
| **D3-R07 — strict input format validation** | Declared ingestion method, MIME and filename extension must agree. CSV uses strict parsing and JSON rejects non-standard constants such as NaN. Separate negative tests cover mismatches, malformed CSV and invalid JSON constants. |
| **D3-R08 — storage failure/recovery** | Missing/corrupt stored bytes persist an explicit FAILED extraction state and reason. Retry clears stale evidence state; re-ingesting identical bytes safely restores missing content-addressed storage without creating duplicate revisions. |
| **D3-R09 — secret-safe logging** | Application logging redacts token/key/password query values and authorization material. httpx/httpcore request logging is suppressed below WARNING. Regression captures logs with a synthetic token and proves it is absent while a positive-control log remains visible. |
| **D3-R10 — metadata-only governed revisions** | Revision identity is source + content checksum + source-snapshot checksum. Material metadata changes stage a new candidate even when bytes are unchanged; active source metadata remains unchanged until approval/activation. Diff reports metadata changes and official pattern-drift candidacy. |

## Corrective schema revision

Alembic revision **20261003_0006** adds:

- source organization/institution/teacher ownership columns and constraints;
- metadata-aware source revision identity;
- source snapshot checksum;
- extracted checksum;
- validated checksum;
- approval fingerprint;
- strict active-status/active-slot invariant.

Earlier Day-3 migration history remains intact.

## Rework regression evidence

Dedicated suites:

- `backend/tests/test_day3_rework_closure.py`
- `backend/tests/test_day3_rework_migration.py`
- existing `test_source_intelligence.py`
- existing `test_source_intelligence_migration.py`

The first fully green rework candidate was GitHub Actions run **#113**, where:

- Ruff passed;
- Mypy passed;
- **95 tests passed**;
- canonical-domain verification passed;
- Source Intelligence verification passed;
- migration round-trip and Alembic drift check passed;
- frontend typecheck/build passed;
- Docker Compose smoke, documented make commands, environment checks and SQLite restart persistence passed.

A final exact-head run is still required after this documentation/state commit; the final handoff must cite that later run rather than treating #113 as the immutable handoff revision.

## Scope boundaries retained

The rework does not implement Day-4 curriculum population, live AnythingLLM/RAG, OCR,
LangGraph generation, public Source CRUD/auth, or final React Admin UI.

## Founder gate

After the exact final revision and post-merge develop CI are green, Day 3 returns to Founder review.
Day 4 stays locked until explicit Founder Day-3 signoff.
