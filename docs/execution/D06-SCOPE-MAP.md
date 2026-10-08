# D6-01 — Day 6 scope map (authoritative PR handoff)

| Task | Implementation | Tests / evidence |
|------|----------------|------------------|
| D6-01 | This document | PR + `D06-DELIVERY-EVIDENCE.md` |
| D6-02 | `app/education_intelligence/registry.py`, `service.py` | `test_day6_validators.py` |
| D6-03 | `app/education_intelligence/contracts.py` (`ValidationResult`) | validator tests |
| D6-04 | `taxonomy_registry.py`, `models/education_intelligence.py` | idempotent test |
| D6-05 | `validators/taxonomy.py` | positive/adversarial |
| D6-06 | `validators/taxonomy.py` | competency duplicate/unknown |
| D6-07 | `validators/alignment.py` (`LearningOutcomeValidator`) | wrong version fixture |
| D6-08 | `validators/alignment.py` (`SourceBackedCompetencyValidator`) | official claim path |
| D6-09 | `contracts.py` (`CognitiveDemandEvidence`) | demand validator |
| D6-10 | `validators/cognition.py` (`TargetObservedCognitiveValidator`) | mismatch fixture |
| D6-11 | `validators/cognition.py` (`CognitiveProgressionValidator`) | progression tests |
| D6-12 | `contracts.py` (`DifficultyEvidence`) | difficulty profile fields |
| D6-13 | `validators/difficulty_age_quality.py` (`DifficultyValidator`) | difficulty evidence |
| D6-14 | `validators/difficulty_age_quality.py` (`AgeGradeAppropriatenessValidator`) | day6_verify |
| D6-15 | `validators/difficulty_age_quality.py` (`StructuralClarityValidator`) | structural failures |
| D6-16 | `validators/difficulty_age_quality.py` (`EducationalQualityRulePackValidator`) | quality rules |
| D6-17 | `contracts.py` (`CanonicalRubric`) | rubric model |
| D6-18 | `validators/rubric_policy_safety.py` (`RubricIntegrityValidator`) | broken rubric |
| D6-19 | `policy_registry.py`, `ei_policy_registry` table | policy version on results |
| D6-20 | `policy_registry.py` (`rules_for_scope`) | override weakening test |
| D6-21 | `validators/rubric_policy_safety.py` (`InstitutionOverrideBoundaryValidator`) | isolation |
| D6-22 | `validators/rubric_policy_safety.py` (`BiasFairnessSafetyValidator`) | safety fixture |
| D6-23 | `enums.py` (`EvidenceAuthority`) | authority enum test |
| D6-24 | `composition.py` (`bind_provenance`) | hash + versions on results |
| D6-25 | `composition.py` (`run_validation`) | composed run tests |
| D6-26 | `ValidationResult.blocking` + severities | blocking failure semantics |
| D6-27 | `explain.py` | explanations in verify report |
| D6-28 | `audit.py`, `ei_validation_audit_runs` | audit persistence test |
| D6-29 | deterministic rerun test | `test_deterministic_rerun` |
| D6-30 | `service.py`, `day6_verify.py` | CLI harness |
| D6-31 | `fixtures.py` CBSE/Telangana | positive fixtures |
| D6-32 | `fixtures.py` adversarial helpers | adversarial tests |
| D6-33 | portable JSON columns | `test_postgres_compile.py` (CI) |
| D6-34 | `migrations/versions/20261007_0010_day6_education_intelligence.py` | migration CI |
| D6-35 | `app/day6_verify.py` | `test_founder_verification_report` |
| D6-36 | `D06-DELIVERY-EVIDENCE.md` | stop gate |

## Explicit exclusions (not implemented on Day 6)

- AnythingLLM / RAG (Day 7)
- LangGraph orchestration (Day 8)
- Diagnostic distractor generation (Day 9)
- Prerequisite / root-cause diagnostics (Day 10)
- **Paper-level cognitive/competency distribution engine (Day 10)** — Day 6 only validates per-item cognition and explicit cognitive-progression primitives
- Exam paper planners / generation (later examination days)
- Learner adaptation (Days 15–16)
- Public REST / MCP product contracts for validation (Day 17)
- Final React product surfaces (Day 18)

D5-DS01 / issue #16 remains deferred; Day 6 does not ingest or verify live Telangana authoritative sources.
