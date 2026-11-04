# D10-R21 — Founder decision: mapping and mandatory-policy curator identity

**Founder decision (2026-11-02): Option A approved.** Option B (defer approvals to Day 17) is **not** selected.

This authorizes the minimal internal authenticated curator-approval implementation in Day 10 for (1) root-cause misconception→concept mapping claims and (2) generic board/institution/teacher mandatory paper-distribution policy claims. It does **not** constitute Day-10 Founder D10-36 signoff (`founder_approval` remains false until explicit D10-36 acceptance).

## Problem (historical)

Day 10 production authorization for **root-cause mapping claims** and **paper mandatory-policy claims** depended on caller-reachable attestation surfaces:

- `MappingClaimWriterAttestation` (see `D10-R19-MAPPING-WRITER-AUTH-DESIGN.md`) was mintable by any code path that could call `issue_mapping_claim_writer_attestation()` with a matching curator `AdminActor`.
- `approve_mandatory_policy_claim()` accepted `actor_id` when it matched `SourceRevision.approved_by` or values listed in the rule’s mutable `metadata_json.mandatory_claim_approver_actor_ids`.

R21 tightened **source locator grounding**, **rule lifecycle digests**, and **read-path revalidation**, but did **not** introduce a non-forgeable trusted principal. **R23 (Option A)** replaces those legacy paths.

## Option A — Minimal internal authenticated approval role (Day 10 exception) — **IMPLEMENTED (R23)**

Internal-only boundary (no new public REST/MCP):

1. **Operator credentials:** scrypt-hashed secrets in `curator_operator_credentials`, bound to active `AdminActor`, scoped org/institution (and board/teacher where applicable), separate roles `mapping_curator` and `mandatory_policy_curator`.
2. **Short-lived write decisions:** HMAC-SHA256 tokens (`CURATOR_APPROVAL_SIGNING_KEY`, distinct from `API_SECRET_KEY`) with `jti` replay protection via `curator_decision_nonces`.
3. **Durable signed audit payloads:** `curator_approval` block on mapping/mandatory `SourceAuditEvent` payloads; verified at production read (`mapping_claim_authorized_for_overlay`, `mandatory_policy_claim_active`).
4. Legacy writer attestation and rule-metadata actor lists **disabled** for production writes; unsigned pre-R23 audit events do not authorize production reads.

**Provisioning:** privileged offline/internal setup only (Founder configures signing key and operator secrets out of band). Tests use randomly generated secrets via `tests/day10_curator_auth.py`.

**Scope:** mapping claim approval + mandatory policy claim approval only. Does not solve full Day 17 user OAuth.

## Option B — Fail-closed deferral to Day 17 — **NOT SELECTED**

## Governance

- PR #29 remains **Draft/unmerged** until explicit Founder D10-36 signoff.
- Day **11 LOCKED**; D5-DS01 **#16 OPEN**; localhost/Docker UAT **deferred, not passed**.
