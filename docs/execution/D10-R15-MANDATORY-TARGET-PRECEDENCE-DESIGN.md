# D10-R15 — Mandatory distribution target precedence (design proposal)

**Status:** PARTIAL — not implemented in Round 15. Founder/design review required before write authority.

## Gap

`paper_distribution/target_policy_registry.py` loads a single global `ei_policy_registry` row (`paper-distribution-targets@v1`). It does not resolve `PolicyRule` rows scoped to board, institution, or teacher with priority, effective dates, or linked `SourceRevision` authority.

D10-28 / D10-29 require **board > institution > teacher** mandatory target precedence without inventing exam-specific blueprints.

## Minimal approved contract (SQLite + PostgreSQL compatible)

1. **Policy key:** `paper_distribution_mandatory_targets` on `PolicyRule` with `value_json` carrying cognitive/competency mandatory exact_count, exact_percent, and min/max ranges (same shape as today’s registry payload subsets).
2. **Scope:** `scope_type` in `{board, institution, teacher}` with `scope_code` matching authenticated `PaperExecutionContext` (board from institution metadata, not free-form client input).
3. **Authority:** each rule links to one or more active `SourceRevision` IDs via `policy_rule_sources`; resolver rejects foreign, revoked, superseded, or curriculum-unbound revisions.
4. **Precedence:** sort by scope rank (board=3, institution=2, teacher=1), then `priority`, then `effective_from`. Lower scope may **tighten** compatible ranges but must not contradict superior mandatory exact_count / exact_percent / range intersection results.
5. **Write path:** internal service method (no public REST) records rule activation only after source revision approval + optional `SourceAuditEvent` `paper_target_policy_approved` mirroring mapping-claim pattern.
6. **Merge:** `merge_mandatory_distribution_targets` consumes resolver output instead of a single global registry row; voluntary caller targets remain separate and audited.

## Tests required when implemented

- Two institutions under one board: board mandatory applies to both; institution tightening passes; institution weakening fails.
- Foreign / expired / revoked source-backed rule ignored.
- Teacher cannot disable board mandatory category.

## Round 15 action

Document only. `D10-SCOPE-MAP.md` keeps D10-28 / D10-29 **PARTIAL**.
