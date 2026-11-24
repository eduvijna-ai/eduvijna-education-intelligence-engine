# Day 15 — Mastery model v1 (D15-18)

**Policy version:** `mastery-policy@v1`  
**Status:** Engineering specification for bounded deterministic updates; not IRT/BKT calibrated.

## Formula

For each `(learner_id, concept_code, policy_version)`:

- **State:** `UNKNOWN` | `EMERGING` | `DEVELOPING` | `SECURE` | `REGRESSION_FLAGGED`
- **Support score:** `correct_eligible = count(scored_correct)` minus counterevidence corrections  
  `incorrect_eligible = count(scored_incorrect)` on mapped concept  
  `attempts = correct_eligible + incorrect_eligible` (distinct finalized attempt items only)
- **Recent window:** last `N=10` eligible item events by `observed_at` (not client timestamps)
- **Recency weight:** events in window weight `1.0`; older events weight `0.25` in support tally
- **Thresholds (within window):**
  - `UNKNOWN`: `attempts < 2`
  - `EMERGING`: `attempts >= 2` and accuracy `< 0.4`
  - `DEVELOPING`: `0.4 <= accuracy < 0.75`
  - `SECURE`: `accuracy >= 0.75` and `correct_eligible >= 3`
  - `REGRESSION_FLAGGED`: last 3 eligible outcomes all incorrect after prior `DEVELOPING` or `SECURE`

## Uncertainty

- **Confidence band:** `LOW` if `attempts < 5`, else `MEDIUM` if `attempts < 15`, else `HIGH`
- No psychometric θ or posterior claims; labels are operational only.

## Cold start

- New concept mapping → `UNKNOWN` (never `0` or implicit mastery).

## Counterevidence

- Authorized correction records retract prior item evidence; mastery recompute is full replay from immutable events.

## Limitations

- Unmapped concept/LO → excluded from rollups (`UNCLASSIFIED`).
- Single unsupported observation never produces diagnosis (D15-24..27).
- Pending descriptive rubric marks do not enter mastery (D15-12).

## Rollups (D15-20..23)

- Topic/curriculum: denominator = mapped concepts with at least one observation; coverage = observed/mapped.
- Multi-tagged items: count once per concept tag (no double count within same item).
- Exam performance: isolated by `exam_pack_code`, `exam_version_id`, `performance_mode` (practice vs synthetic_official).