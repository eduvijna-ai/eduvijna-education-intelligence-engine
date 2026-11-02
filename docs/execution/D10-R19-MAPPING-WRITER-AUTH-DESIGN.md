# D10-R19 — Mapping claim writer attestation (Day 10 partial boundary)

## Decision

Day 10 mapping claim writes require a **`MappingClaimWriterAttestation`** issued only through
`issue_mapping_claim_writer_attestation()` after the same **AdminActor + curator registry** checks
used at approval time. Approval rejects user-constructible attestation refs that do not match the
approval context digest.

This is **not** a substitute for Day 17 authenticated principals (OAuth/session-bound actor). Any
internal caller that can invoke `approve_root_cause_mapping_claim` can still mint a valid attestation
for an authorized curator. **D10-12 remains PARTIAL** until a non-forgeable trusted boundary exists.

## Minimum Day 17 follow-up

- Inject an opaque `TrustedWriterPrincipal` from orchestration/API layers only; attestation must not
  be constructible from test/caller code paths in production builds.
- Bind writer attestation to control-session lease or signed service token.

## Risk accepted for Day 10

Curator impersonation across *mismatched* actor IDs is blocked; teacher-scoped **claim_id** includes
`teacher_id` so revocation is per-teacher.
