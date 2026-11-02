# D10-R21 — Founder decision: mapping and mandatory-policy curator identity

## Problem

Day 10 production authorization for **root-cause mapping claims** and **paper mandatory-policy claims** still depends on caller-reachable attestation surfaces:

- `MappingClaimWriterAttestation` (see `D10-R19-MAPPING-WRITER-AUTH-DESIGN.md`) is mintable by any code path that can call `issue_mapping_claim_writer_attestation()` with a matching curator `AdminActor`.
- `approve_mandatory_policy_claim()` accepts `actor_id` when it matches `SourceRevision.approved_by` or values listed in the rule’s mutable `metadata_json.mandatory_claim_approver_actor_ids`.

R21 tightens **source locator grounding**, **rule lifecycle digests**, and **read-path revalidation**, but does **not** introduce a third self-attested token. Without a non-forgeable trusted principal, **D10-12** and **D10-28/29** remain honestly **PARTIAL**.

## Option A — Minimal internal authenticated approval role (Day 10 exception)

Implement a small **internal-only** service boundary (no new public REST/MCP) that:

1. Issues short-lived, signed **policy/mapping curator decisions** bound to control-session lease or service token (opaque to business callers).
2. Replaces direct `actor_id` + writer attestation acceptance in production paths with verification of that signed decision at write **and** read time.
3. Keeps SQLite/PostgreSQL-compatible audit events; maps decisions to existing `SourceAuditEvent` / orchestration audit tables.

**Scope:** mapping claim approval + mandatory policy claim approval only. Does not solve full Day 17 user OAuth.

## Option B — Fail-closed deferral to Day 17

Until Day 17 authenticated principals exist:

1. Production **mapping overlay activation** and **board mandatory-policy claim activation** remain disabled (fixture/synthetic modes only).
2. Document explicit Founder-approved **exceptions** to D10-12/28 acceptance criteria for v1.0 Day 10 signoff, OR move those tasks to Day 17 with revised scope map.

## Request

Founder to choose **A** or **B** (or a hybrid with written scope). Engineering will not self-select B or mark D10-12/28 IMPLEMENTED without that decision.
