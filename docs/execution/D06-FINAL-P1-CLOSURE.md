# Day 6 — Final P1 Closure

Day 6 remains ACTIVE and is not Founder-approved.

This correction exists only to close the two P1 findings from the final Codex review of `d36eb0991eddf80e8957cd5c079fa72b1bdecfcd`.

## P1-01 — Inactive official competency must not authorize PASS

Current risk:
- `SourceBackedCompetencyValidator` may select a matching competency entity with `active=False`.
- If scope and SourceRevision are otherwise valid, the retired competency can authorize an official PASS.

Required behavior:
- official competency resolution must reject inactive/retired competency entities;
- only an active competency entity with valid exact scope and ACTIVE SourceRevision may authorize a new official PASS;
- generic taxonomy tagging remains separate and unaffected.

Targeted tests:
- active competency + valid source/scope -> eligible;
- inactive competency + valid source/scope -> FAIL;
- inactive competency must never contribute official evidence/provenance as a passing claim.

## P1-02 — Incomplete age claims must not incorrectly PASS

Current risk:
- authoritative age-band comparison only rejects mismatches when both `age_min` and `age_max` are supplied;
- a single impossible bound can bypass comparison and reach PASS.

Required behavior:
- if an authoritative band exists, validate every supplied bound independently;
- `age_min` above authoritative maximum -> FAIL;
- `age_max` below authoritative minimum -> FAIL;
- a single supplied bound that cannot establish full appropriateness but is not contradictory -> `review_required`, not PASS;
- complete compatible ranges may PASS;
- missing authoritative mapping remains `review_required`.

Targeted tests:
- authoritative 12–14 + age_min=99, age_max=None -> FAIL;
- authoritative 12–14 + age_min=None, age_max=4 -> FAIL;
- authoritative 12–14 + age_min=12 only -> review_required;
- authoritative 12–14 + age_max=14 only -> review_required;
- complete compatible 12–14 -> PASS.

## Founder verifier update

`python -m app.day6_verify` must explicitly demonstrate:
- inactive official competency cannot authorize PASS;
- incomplete age claims cannot incorrectly PASS.

## Test policy

For this correction:
- run Ruff only on changed Python files;
- run Mypy only on affected Day 6 modules if needed;
- run only the directly affected Day 6 tests plus `day6_verify`;
- no full historical backend suite;
- no Compose run unless Docker/config changes;
- no migration checks unless schema changes.

After targeted checks are green, request Codex re-review on the exact correction SHA.

## Governance

- Day 6: ACTIVE / not Founder-approved
- Day 7: LOCKED
- D5-DS01 / issue #16: unchanged
- no Day 7 implementation
- no Day 10 distribution work
- do not merge until Codex has no blocker/P1/major findings and Founder explicitly signs off Day 6.
