from __future__ import annotations

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    DifficultyEvidence,
    ValidationResult,
)
from app.education_intelligence.enums import ValidationSeverity, ValidationStatus

QUALITY_RULES_V1 = [
    {
        "rule_code": "QUAL-ALIGN-001",
        "description": "Stem must not be empty",
        "severity": ValidationSeverity.MANDATORY,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-CLAR-001",
        "description": "Single choice requires at least two options",
        "severity": ValidationSeverity.MANDATORY,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-ANS-001",
        "description": "Answer metadata must be present when required",
        "severity": ValidationSeverity.MANDATORY,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-EXPL-001",
        "description": "Explanation required when flagged",
        "severity": ValidationSeverity.MANDATORY,
        "blocking": True,
    },
    {
        "rule_code": "QUAL-TRICK-001",
        "description": "Avoid trick wording patterns",
        "severity": ValidationSeverity.ADVISORY,
        "blocking": False,
    },
]


class DifficultyValidator:
    validator_id = "difficulty_profile"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        declared = item.declared_difficulty
        profile = item.difficulty_evidence
        if declared is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.NOT_APPLICABLE,
                rule_codes=["DIFF-000"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={},
                observed={},
                taxonomy_version=ctx.taxonomy.version,
            )
        if profile is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["DIFF-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"declared_difficulty": declared},
                observed={"profile": None},
                taxonomy_version=ctx.taxonomy.version,
            )
        inferred = _infer_difficulty_band(profile)
        if inferred is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["DIFF-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"declared_difficulty": declared},
                observed={"inferred_band": None, "profile": profile.model_dump()},
                taxonomy_version=ctx.taxonomy.version,
            )
        delta = abs(inferred - declared)
        if delta >= 2:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["DIFF-003"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"declared_difficulty": declared},
                observed={
                    "inferred_band": inferred,
                    "profile": profile.model_dump(),
                    "design_time_only": True,
                },
                taxonomy_version=ctx.taxonomy.version,
            )
        if delta == 1:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.WARN,
                rule_codes=["DIFF-004"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"declared_difficulty": declared},
                observed={"inferred_band": inferred, "profile": profile.model_dump()},
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["DIFF-005"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"declared_difficulty": declared},
            observed={"inferred_band": inferred, "profile": profile.model_dump()},
            taxonomy_version=ctx.taxonomy.version,
        )


def _infer_difficulty_band(profile: DifficultyEvidence) -> int | None:
    signals = [
        profile.cognitive_demand_band,
        profile.abstraction_level,
        profile.computation_load,
        profile.language_load,
    ]
    present = [s for s in signals if s is not None]
    if not present:
        return None
    avg = sum(present) / len(present)
    if profile.step_count is not None and profile.step_count >= 4:
        avg += 0.5
    return int(max(1, min(5, round(avg))))


class AgeGradeAppropriatenessValidator:
    validator_id = "age_grade_appropriateness"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        authoritative = bool(item.metadata_json.get("authoritative_age_mapping"))
        if (
            ctx.curriculum_index
            and item.grade_year_code
            and item.grade_year_code in ctx.curriculum_index.grade_authoritative_age
        ):
            authoritative = True
        if item.grade_year_code and not authoritative:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["AGE-001"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"grade_year_code": item.grade_year_code},
                observed={"authoritative_age_mapping": False},
                taxonomy_version=ctx.taxonomy.version,
            )
        if item.age_min is None and item.age_max is None and not item.grade_year_code:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["AGE-001"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"grade_year_code": item.grade_year_code},
                observed={"authoritative_age_mapping": False},
                taxonomy_version=ctx.taxonomy.version,
            )
        if item.age_min is not None and item.age_max is not None and item.age_min > item.age_max:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["AGE-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"age_min": item.age_min, "age_max": item.age_max},
                observed={"invalid_range": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        if item.language_complexity_flag == "excessive" and (item.age_max or 99) <= 12:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.WARN,
                rule_codes=["AGE-003"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"language_complexity_flag": item.language_complexity_flag},
                observed={"young_learner": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        if item.sensitive_context and not item.metadata_json.get("sensitive_context_reviewed"):
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["AGE-004"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"sensitive_context": True},
                observed={"review_flag_missing": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["AGE-005"],
            severity=ValidationSeverity.ADVISORY,
            blocking=False,
            target={
                "grade_year_code": item.grade_year_code,
                "age_min": item.age_min,
                "age_max": item.age_max,
            },
            observed={"appropriate": True},
            taxonomy_version=ctx.taxonomy.version,
        )


class StructuralClarityValidator:
    validator_id = "structural_clarity"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        stem = (item.stem_text or "").strip()
        if not stem:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["STRUCT-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"stem_text": item.stem_text},
                observed={"empty_stem": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        if item.question_type == "single_choice":
            if len(item.options) < 2:
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["STRUCT-002"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"options_count": len(item.options)},
                    observed={"malformed_options": True},
                    taxonomy_version=ctx.taxonomy.version,
                )
            texts = [o.text.strip().lower() for o in item.options if o.text.strip()]
            if len(texts) != len(set(texts)):
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["STRUCT-003"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"options": [o.option_key for o in item.options]},
                    observed={"duplicate_options": True},
                    taxonomy_version=ctx.taxonomy.version,
                )
            if not any(o.is_correct for o in item.options):
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["STRUCT-004"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"options": len(item.options)},
                    observed={"missing_correct_answer": True},
                    taxonomy_version=ctx.taxonomy.version,
                )
        if not item.notation_asset_refs_valid:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["STRUCT-005"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"notation_asset_refs_valid": False},
                observed={"invalid_notation": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        if "see figure" in stem.lower() and "fig_" not in item.metadata_json.get("asset_refs", []):
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["STRUCT-006"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"stem_text": stem},
                observed={"unresolved_reference": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["STRUCT-007"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"stem_length": len(stem)},
            observed={"structural_ok": True},
            taxonomy_version=ctx.taxonomy.version,
        )


class EducationalQualityRulePackValidator:
    validator_id = "educational_quality_rules"
    validator_version = "1.1.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        pack = ctx.quality_rule_pack
        if pack is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["QUAL-PACK-000"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={},
                observed={"quality_rule_pack": None},
                taxonomy_version=ctx.taxonomy.version,
            )
        rule_codes: list[str] = []
        status = ValidationStatus.PASS
        blocking = False
        observed: dict[str, object] = {"quality_rule_pack_version": pack.version}
        stem = item.stem_text.strip()
        trick_patterns = ("all of the above are wrong", "none of these", "trick question")
        lower = stem.lower()
        for rule in pack.rules:
            code = str(rule.get("rule_code", ""))
            check = str(rule.get("check", ""))
            is_blocking = bool(rule.get("blocking", False))
            triggered = False
            if check == "non_empty_stem" and not stem:
                triggered = True
            elif check == "single_choice_min_options" and item.question_type == "single_choice":
                triggered = len(item.options) < 2
            elif check == "answer_metadata_present":
                triggered = not item.answer_metadata_present
            elif check == "explanation_when_required":
                triggered = item.explanation_required and not item.explanation_present
            elif check == "avoid_trick_wording":
                triggered = any(p in lower for p in trick_patterns)
            if triggered:
                rule_codes.append(code)
                if is_blocking:
                    status = ValidationStatus.FAIL
                    blocking = True
                elif status == ValidationStatus.PASS:
                    status = ValidationStatus.WARN
        if not rule_codes:
            rule_codes = ["QUAL-PASS-001"]
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=status,
            rule_codes=rule_codes,
            severity=ValidationSeverity.MANDATORY if blocking else ValidationSeverity.ADVISORY,
            blocking=blocking,
            target={"quality_rule_pack_version": pack.version},
            observed=observed,
            taxonomy_version=ctx.taxonomy.version,
        )
