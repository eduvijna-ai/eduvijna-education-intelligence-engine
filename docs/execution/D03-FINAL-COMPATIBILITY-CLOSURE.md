# D03 — Final Compatibility Closure

Status: **ENGINEERING COMPLETE / FOUNDER REVIEW**

Day 4: **LOCKED**

This closes the final Day-3 compatibility findings D3-R11 and D3-R12 without changing the
previously closed D3-R01 through D3-R10 scope.

## D3-R11 — Legacy revision evidence migration

The `0005 -> 0006` path now computes `source_snapshot_checksum` from the canonical stored
`source_snapshot` instead of copying the document checksum.

Legacy candidate states whose new evidence binding cannot be proven are made safe:

- file/URL `extracted`, `validated`, and `approved` candidates return to `staged` and
  must be re-extracted, revalidated, and reapproved;
- manual `validated` / `approved` candidates return to `extracted`, because their canonical
  manual metadata bytes can be recomputed and verified;
- `active` and `superseded` revisions retain lifecycle state while receiving corrected snapshot
  and legacy validation checksum fields;
- legacy approval fingerprints are never invented.

Alembic revision `20261003_0007` is an idempotent data repair for installations that had already
applied the earlier version of `0006`. It only repairs rows whose stored snapshot checksum does not
match their actual canonical snapshot.

Regression coverage includes staged, extracted, validated, approved, active, superseded, and manual
legacy revision states, plus simulation of an already-applied old-`0006` row.

## D3-R12 — Legacy tenant-source ownership compatibility

The revised `0006` preflights all `institution_content` and `teacher_content` rows while the
database is still on `0005`.

Ownership is never guessed.

If ownership is missing or invalid:

1. migration fails before schema modification;
2. the database remains at `20261002_0005`;
3. affected source IDs are included in the error;
4. Founder/engineering can inspect and explicitly stage ownership;
5. migration can then be retried safely.

Internal repair commands:

```bash
cd backend
python -m app.source_legacy_repair inspect
python -m app.source_legacy_repair apply --mapping legacy-source-ownership.json
alembic upgrade head
```

Example mapping:

```json
{
  "<source-id>": {
    "organization_id": "<organization-id>",
    "institution_id": "<institution-id>",
    "teacher_id": null
  },
  "<teacher-source-id>": {
    "organization_id": "<organization-id>",
    "institution_id": "<institution-id>",
    "teacher_id": "<teacher-id>"
  }
}
```

The mapping must cover every legacy tenant-owned source exactly. The utility validates organization,
institution, and teacher relationships before staging the repair marker.

Regression coverage proves:

- unowned legacy tenant sources fail migration atomically;
- no partial ownership columns remain after failure;
- invalid ownership mappings are rejected;
- valid explicit mappings allow a successful retry to head;
- ownership columns and foreign keys are correct after retry.

## Migration head

Final Day-3 migration head:

`20261003_0007`

## Verification

The first green compatibility candidate, GitHub Actions run #120, passed:

- Ruff;
- Mypy;
- **99 tests**;
- canonical-domain verification;
- Source Intelligence verification;
- migration round-trip and Alembic drift check;
- frontend typecheck/build;
- Docker Compose startup;
- documented make commands;
- environment checks;
- SQLite restart persistence.

A later exact-head run after this documentation/state commit is required for the immutable handoff.

## Founder gate

Day 3 remains at Founder review. Day 4 remains locked until explicit Day-3 signoff.
