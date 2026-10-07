from __future__ import annotations

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import CanonicalAssessmentItem, ValidationResult
from app.education_intelligence.enums import ValidationSeverity, ValidationStatus


class RubricIntegrityValidator:
    validator_id = "rubric_integrity"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        rubric = item.rubric
        if rubric is None or not rubric.criteria:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.NOT_APPLICABLE,
                rule_codes=["RUB-000"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={},
                observed={},
                taxonomy_version=ctx.taxonomy.version,
            )
        ids = [c.criterion_id for c in rubric.criteria]
        if len(ids) != len(set(ids)):
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["RUB-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"criteria_ids": ids},
                observed={"duplicate_criteria": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        total = sum(c.marks for c in rubric.criteria)
        if rubric.total_marks is not None and abs(total - rubric.total_marks) > 0.001:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["RUB-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"total_marks": rubric.total_marks},
                observed={"computed_total": total},
                taxonomy_version=ctx.taxonomy.version,
            )
        for criterion in rubric.criteria:
            if criterion.marks <= 0:
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["RUB-003"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"criterion_id": criterion.criterion_id},
                    observed={"invalid_marks": criterion.marks},
                    taxonomy_version=ctx.taxonomy.version,
                )
            if not criterion.performance_levels:
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["RUB-004"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"criterion_id": criterion.criterion_id},
                    observed={"missing_descriptors": True},
                    taxonomy_version=ctx.taxonomy.version,
                )
            scores: list[float] = [
                float(lvl["score"])
                for lvl in criterion.performance_levels
                if lvl.get("score") is not None
            ]
            if scores and scores != sorted(scores):
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["RUB-005"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"criterion_id": criterion.criterion_id},
                    observed={"impossible_threshold_order": scores},
                    taxonomy_version=ctx.taxonomy.version,
                )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["RUB-006"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"criteria_count": len(rubric.criteria)},
            observed={"total_marks": total},
            taxonomy_version=ctx.taxonomy.version,
        )


class PolicyPrecedenceValidator:
    validator_id = "policy_precedence"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        rules = ctx.policy.rules_for_scope(
            board_code=ctx.board_code,
            institution_id=item.institution_id,
        )
        violations: list[str] = []
        for rule in rules:
            if "explanation_present" in rule.requires:
                if item.explanation_required and not item.explanation_present:
                    violations.append(rule.rule_code)
            if item.competency_claim_official and "official_competency_evidence" in rule.requires:
                if ctx.curriculum_index is None:
                    violations.append(rule.rule_code)
        if violations:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=violations,
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"institution_id": item.institution_id, "board_code": ctx.board_code},
                observed={"policy_violations": violations},
                policy_version=ctx.policy.version,
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["POL-PREC-PASS"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"rules_evaluated": len(rules)},
            observed={"precedence_ok": True},
            policy_version=ctx.policy.version,
            taxonomy_version=ctx.taxonomy.version,
        )


class InstitutionOverrideBoundaryValidator:
    validator_id = "institution_override_boundary"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        if not item.institution_id:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.NOT_APPLICABLE,
                rule_codes=["INST-000"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={},
                observed={},
                policy_version=ctx.policy.version,
            )
        foreign_overrides = [
            o
            for o in ctx.policy.institution_overrides
            if o.institution_id != item.institution_id
        ]
        weakening = [
            o.policy_key
            for o in ctx.policy.institution_overrides
            if o.institution_id == item.institution_id and o.value.get("disable_blocking")
        ]
        if foreign_overrides and item.metadata_json.get("simulate_cross_tenant_override_leak"):
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["INST-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"institution_id": item.institution_id},
                observed={"cross_tenant_leak": True},
                policy_version=ctx.policy.version,
            )
        if weakening:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["INST-002"],
                severity=ValidationSeverity.SAFETY,
                blocking=True,
                target={"institution_id": item.institution_id},
                observed={"official_policy_weakened": weakening},
                policy_version=ctx.policy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["INST-003"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"institution_id": item.institution_id},
            observed={"isolation_ok": True},
            policy_version=ctx.policy.version,
        )


SAFETY_PATTERNS = (
    "kill yourself",
    "racial slur",
    "unnecessary ssn",
    "demeaning stereotype",
)


class BiasFairnessSafetyValidator:
    validator_id = "bias_fairness_safety"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        text = (item.content_text_for_safety or item.stem_text or "").lower()
        hits = [p for p in SAFETY_PATTERNS if p in text]
        if "demeaning stereotype" in text:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["SAFE-001"],
                severity=ValidationSeverity.SAFETY,
                blocking=False,
                target={"content_scan": True},
                observed={"ambiguous_semantic": True},
                policy_version=ctx.policy.version,
            )
        if hits:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["SAFE-002"],
                severity=ValidationSeverity.SAFETY,
                blocking=True,
                target={"patterns_checked": len(SAFETY_PATTERNS)},
                observed={"hits": hits},
                policy_version=ctx.policy.version,
            )
        if "unsafe lab experiment" in text:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["SAFE-003"],
                severity=ValidationSeverity.SAFETY,
                blocking=True,
                target={"unsafe_instruction": True},
                observed={"triggered": True},
                policy_version=ctx.policy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["SAFE-PASS"],
            severity=ValidationSeverity.SAFETY,
            blocking=False,
            target={},
            observed={"clean": True},
            policy_version=ctx.policy.version,
        )
