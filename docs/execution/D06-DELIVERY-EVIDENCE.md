# Day 6 — Education Intelligence Validators (delivery evidence)

## Status

- **Day 6 engineering**: correction iteration #1 on branch `feature/day6-education-intelligence-validators`
- **Founder approval**: not requested (separate gate)
- **D5-DS01 / issue #16**: unchanged — verified via `verify_governance_state()` in `day6_verify`
- **Exact-head proof**: supplied by CI run on the correction candidate SHA (not embedded as a mutable SHA in this document per C6-R12)

## Failed baseline (iteration anchor)

- Base failed SHA: `4775c2379ac46af2eab8f3d5ba0e66957c16545e`
- Failed CI: run #209 — backend job, Ruff import-order gate

## Correction scope map (C6-R01…C6-R15)

| ID | Implementation |
|----|----------------|
| C6-R01 | Ruff import order (`fixtures.py`, `models/__init__.py`) + `ruff check app tests` |
| C6-R02 | `validators/alignment.py` + `scope.py` exact LO scope |
| C6-R03 | `SourceBackedCompetencyValidator` scoped framework/version/subject |
| C6-R04 | `AgeGradeAppropriatenessValidator` authoritative mapping gate |
| C6-R05 | `policy_registry.py` — weakening overrides ignored, authoritative rules kept |
| C6-R06 | Foreign overrides ignored; tests without simulation metadata |
| C6-R07 | `RubricIntegrityValidator` weights/links/thresholds |
| C6-R08 | `quality_rule_pack.py` + persisted `ei_quality_rule_packs` |
| C6-R09 | `safety_rules.py` versioned policy payload + validator |
| C6-R10 | `bind_provenance` + `source_entity_refs` on alignment results |
| C6-R11 | `governance.py` + hardened `day6_verify.py` |
| C6-R12 | This document — CI/PR supplies exact SHA |
| C6-R13 | `tests/test_day6_corrections.py` |
| C6-R14 | Full gate on correction candidate (CI + local commands below) |
| C6-R15 | Codex review after green CI |

## Local verification commands

```bash
cd backend
ruff check app tests
mypy app
PATH="$PWD/.venv/bin:$PATH" pytest -q
python -m app.day6_verify
```

## Review-required limitations

- Cognitive-demand and bias semantics use deterministic rules; ambiguous cases return `review_required`.
- LO/competency without `source_revision_id` on official paths returns `review_required`.
- Telangana authoritative sources remain D5-DS01 deferred.

## Stop gate

Do not merge without Founder signoff. Do not unlock Day 7.
