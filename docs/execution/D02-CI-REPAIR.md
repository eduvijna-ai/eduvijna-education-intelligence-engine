# D02 CI repair record

The first D02 pull-request CI pass reached the backend lint gate and found only five formatting/import-order issues. Frontend typecheck/build was green.

Commit c53f5c5 repairs those Ruff findings without changing D02 behavior or scope.

This normal contents commit also emits a PR synchronization event so the repaired branch receives a fresh CI run.

## ORM persistence repair

The first full pytest pass exposed a real construction issue: prerequisite edges built from unflushed UUID attributes could carry null foreign keys because UUID defaults are assigned on insert.

Commit `bf79bcc` fixes the domain semantics by adding explicit prerequisite/target relationships and version relationships for test definitions, so object graphs can be composed safely before persistence. Tests were updated to use those relationships rather than inserting a manual flush workaround.


## Canonical invariant hardening

Codex's first D02 review identified durable-model risks. The current branch now enforces and tests:

- D01 Founder approval / D02 ACTIVE execution state;
- safe prerequisite relationships for transient UUID-backed objects;
- SQLite foreign keys in runtime, migration connections, synthetic verification and tests;
- sibling code uniqueness regardless of node type;
- root code uniqueness within a curriculum version;
- same-version curriculum parent/child boundaries;
- database-level exact/min/max blueprint consistency.

Regression tests deliberately attempt the invalid writes and require the database to reject them.
