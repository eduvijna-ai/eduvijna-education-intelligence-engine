# Day 7 Production Identity Closure

Founder-authorized controlled closure task created after the original Day 7 review loop exhausted iteration 3/3.

This is a **new task**, not iteration 4 of `day7-knowledge-intelligence-anythingllm`.

Base Day 7 candidate:
`7dca3b976024c4f88632ad20404569b128b96d46`

## Closure objective

Guarantee that every real AnythingLLM vector-search hit can be resolved back to the exact persisted Eduvijna knowledge binding and SourceRevision using an Eduvijna-controlled stable remote identity.

The closure must not trust:
- upload location as equivalent to `docSource`;
- AnythingLLM defaults for `docSource`;
- vector/chunk UUID as document identity;
- request metadata as provenance.

## Required design

### D7-PIC-01 — Stable Eduvijna document identity

Create a deterministic, immutable identity before upload.

It must be derived from governed Eduvijna state such as:
- SourceRevision ID;
- checksum;
- retrieval profile version.

Example shape only:
`eduvijna://knowledge/<source_revision_id>/<profile_version>/<checksum>`

Do not use transient chunk IDs.

### D7-PIC-02 — Send stable identity as supported AnythingLLM metadata

The HTTP adapter must send the stable identity using the supported upload metadata key `docSource`.

Preserve:
- multipart file upload;
- `addToWorkspaces` as documented comma-separated slug string;
- title/author/description metadata as applicable.

### D7-PIC-03 — Verify upload echo before activating binding

Do not assume AnythingLLM preserved `docSource`.

After upload:
- parse `documents[]`;
- require returned document metadata to expose the same `docSource` identity, when the deployed AnythingLLM contract/version supports it;
- if the gateway drops, rewrites, defaults, or omits the requested stable identity, treat the upload as an incompatible/invalid response;
- do **not** mark the binding ACTIVE;
- audit the incompatibility without leaking secrets.

This is mandatory because some AnythingLLM builds have been reported to drop upload metadata.

### D7-PIC-04 — Persist both retrieval identity and removal identity

Persist separately:
- Eduvijna stable `docSource` identity used for retrieval matching;
- AnythingLLM returned location/document identity required for retirement/de-embedding.

Do not overwrite one with the other.

Prefer existing `KnowledgeSourceBinding.metadata_json` for this closure unless a real schema requirement is proven. Avoid a migration if metadata storage is sufficient.

### D7-PIC-05 — Vector-hit exact binding resolution

For real vector-search hits:
- require `metadata.docSource`;
- match it exactly against the persisted Eduvijna stable identity;
- never fall back to chunk UUID;
- never match from query/request provenance;
- missing or unknown `docSource` => reject/drop with audit-visible warning.

### D7-PIC-06 — Retirement remains location-based

Keep remote retirement/de-embedding using the supported AnythingLLM document location/identity expected by `update-embeddings`.

The stable `docSource` provenance identity is for retrieval binding, not a substitute for the remote removal key unless the gateway contract explicitly proves equivalence.

### D7-PIC-07 — Idempotency

Repeated indexing of the same SourceRevision/checksum/profile:
- reuses the same stable identity;
- does not duplicate bindings;
- does not create a new provenance identity.

### D7-PIC-08 — Mocked HTTP contract tests

Add/adjust Day 7-only tests proving:

1. upload sends:
   - `addToWorkspaces=ws-global`;
   - metadata contains the exact stable `docSource` identity.

2. upload response echoing the exact `docSource`:
   - succeeds;
   - persists stable identity + remote location separately.

3. upload response with default/mismatched/missing `docSource`:
   - fails closed;
   - binding never becomes ACTIVE.

4. vector result:
   `{"id":"chunk-uuid","metadata":{"docSource":"<stable-id>","chunkSource":"..."}}`
   resolves to the exact binding.

5. unknown `docSource`:
   - rejected.

6. chunk UUID alone:
   - never resolves to a binding.

7. retirement still sends the persisted remote location through `update-embeddings`.

### D7-PIC-09 — Founder verifier extension

Extend `python -m app.day7_verify` with deterministic evidence that:
- stable identity is deterministic;
- exact `docSource` is persisted;
- mismatched gateway echo fails closed;
- vector hit maps through stable `docSource`;
- unknown/missing identity is rejected;
- exact SourceRevision provenance is preserved.

No live AnythingLLM dependency is required for core CI.

### D7-PIC-10 — Final closure evidence

Before closure:
- targeted tests green;
- Ruff/Mypy relevant scope green;
- backend-only Compose Day 7 tests green;
- exact-SHA Codex review has no blocker/P1/major issue;
- no additional automatic repair after 3 iterations of this new task;
- original Day 7 PR #22 remains unmerged;
- Day 8 remains LOCKED;
- D5-DS01 / issue #16 remains unchanged.

After this new closure task is independently clean:
- merge this closure into the Day 7 feature branch;
- run the one full Day 7 regression checkpoint on the combined Day 7 head;
- then present Day 7 for Founder signoff.
