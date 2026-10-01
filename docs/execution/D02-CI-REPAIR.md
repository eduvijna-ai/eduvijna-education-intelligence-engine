# D02 CI repair record

The first D02 pull-request CI pass reached the backend lint gate and found only five formatting/import-order issues. Frontend typecheck/build was green.

Commit c53f5c5 repairs those Ruff findings without changing D02 behavior or scope.

This normal contents commit also emits a PR synchronization event so the repaired branch receives a fresh CI run.

## ORM persistence repair

The first full pytest pass exposed a real construction issue: prerequisite edges built from unflushed UUID attributes could carry null foreign keys because UUID defaults are assigned on insert.

Commit `bf79bcc` fixes the domain semantics by adding explicit prerequisite/target relationships and version relationships for test definitions, so object graphs can be composed safely before persistence. Tests were updated to use those relationships rather than inserting a manual flush workaround.


## Canonical invariant hardening

Codex's first D02 review identified durable-model risks. The current branch now enforces and tests:

- D01 UAT deferred by Founder / explicit D02 continuation authorization / D03 locked;
- safe prerequisite relationships for transient UUID-backed objects;
- SQLite foreign keys in runtime, migration connections, synthetic verification and tests;
- sibling code uniqueness regardless of node type;
- root code uniqueness within a curriculum version;
- same-version curriculum parent/child boundaries;
- database-level exact/min/max blueprint consistency.

Regression tests deliberately attempt the invalid writes and require the database to reject them.


## SQLite verification-path alignment

The final FK hardening also makes SQLite foreign-key enforcement consistent in:

- the application engine factory;
- Alembic online migration connections;
- in-memory Founder domain verification;
- the invariant test harness.

Duplicate invariant tests introduced during concurrent repair were removed; the existing file-backed FK-aware regression suite remains authoritative.


## Explicit migration boundary

The D02 migration gate now verifies the exact contract rather than a relative Alembic shorthand:

`20261001_0002 -> 20261001_0001 -> 20261001_0002`.

Both GitHub CI and the documented `make test` path use the explicit D01 revision as the rollback target.


## Founder-state correction

The Founder explicitly deferred D01 localhost UAT until after D02 and explicitly authorized continuation to D02.

The authoritative state is:

- D01 UAT_DEFERRED_BY_FOUNDER;
- D01 founder_approval=false;
- D02 ACTIVE by explicit continuation authorization;
- combined D01 + D02 Founder UAT required after D02;
- D03 LOCKED until the combined Founder acceptance is complete.

PR merge, green CI, or Codex review do not count as Founder approval.
