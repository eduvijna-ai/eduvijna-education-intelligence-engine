from __future__ import annotations

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import CanonicalAssessmentItem, ValidationResult
from app.education_intelligence.enums import ValidationSeverity, ValidationStatus


class RubricIntegrityValidator:
    validator_id = "rubric_integrity"
    validator_version = "1.1.0"

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
        weights = [c.weight for c in rubric.criteria if c.weight is not None]
        if weights and abs(sum(weights) - 1.0) > 0.01 and abs(sum(weights) - 100.0) > 0.01:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["RUB-007"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"weights": weights},
                observed={"invalid_weight_total": sum(weights)},
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
            for level in criterion.performance_levels:
                if not level.get("descriptor") and not level.get("label"):
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
            if scores and max(scores) > criterion.marks:
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["RUB-008"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"criterion_id": criterion.criterion_id},
                    observed={"impossible_threshold": max(scores)},
                    taxonomy_version=ctx.taxonomy.version,
                )
            unresolved_lo = [
                lo_id
                for lo_id in criterion.learning_outcome_ids
                if ctx.curriculum_index is None
                or lo_id not in ctx.curriculum_index.learning_outcomes
            ]
            if unresolved_lo:
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["RUB-009"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"criterion_id": criterion.criterion_id},
                    observed={"unresolved_learning_outcomes": unresolved_lo},
                    taxonomy_version=ctx.taxonomy.version,
                )
            unresolved_comp = []
            for code in criterion.competency_codes:
                resolved, _ = ctx.taxonomy.resolve_competency(code)
                if resolved is None:
                    unresolved_comp.append(code)
            if unresolved_comp:
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["RUB-010"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"criterion_id": criterion.criterion_id},
                    observed={"unresolved_competencies": unresolved_comp},
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
    validator_version = "1.1.0"

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
            if rule.value.get("disable_blocking"):
                violations.append("POL-PREC-WEAKEN")
        if violations:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=violations,
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"institution_id": item.institution_id, "board_code": ctx.board_code},
                observed={"policy_violations": violations, "policy_version": ctx.policy.version},
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
            observed={"precedence_ok": True, "policy_version": ctx.policy.version},
            policy_version=ctx.policy.version,
            taxonomy_version=ctx.taxonomy.version,
        )


class InstitutionOverrideBoundaryValidator:
    validator_id = "institution_override_boundary"
    validator_version = "1.1.0"

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
        rules = ctx.policy.rules_for_scope(
            board_code=ctx.board_code,
            institution_id=item.institution_id,
        )
        if any(r.value.get("disable_blocking") for r in rules):
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["INST-002"],
                severity=ValidationSeverity.SAFETY,
                blocking=True,
                target={"institution_id": item.institution_id},
                observed={"weakening_override_applied": True},
                policy_version=ctx.policy.version,
            )
        foreign_keys = {
            o.policy_key
            for o in ctx.policy.institution_overrides
            if o.institution_id != item.institution_id
        }
        applied_keys = {r.policy_key for r in rules}
        leaked = foreign_keys.intersection(applied_keys)
        if leaked:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["INST-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"institution_id": item.institution_id},
                observed={"cross_tenant_policy_keys": sorted(leaked)},
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
            observed={"isolation_ok": True, "foreign_overrides_ignored": len(foreign_keys)},
            policy_version=ctx.policy.version,
        )


class BiasFairnessSafetyValidator:
    validator_id = "bias_fairness_safety"
    validator_version = "1.1.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        pack = ctx.safety_rule_pack
        text = (item.content_text_for_safety or item.stem_text or "").lower()
        if pack is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["SAFE-PACK-000"],
                severity=ValidationSeverity.SAFETY,
                blocking=False,
                target={},
                observed={},
                policy_version=ctx.policy.version,
            )
        hits: list[str] = []
        review_codes: list[str] = []
        for rule in pack.rules:
            pattern = str(rule.get("pattern", "")).lower()
            if not pattern or pattern not in text:
                continue
            code = str(rule.get("rule_code", "SAFE-UNK"))
            if rule.get("review_required"):
                review_codes.append(code)
            elif rule.get("blocking", True):
                hits.append(code)
        if hits:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=hits,
                severity=ValidationSeverity.SAFETY,
                blocking=True,
                target={"safety_rules_version": pack.version},
                observed={
                    "rule_hits": hits,
                    "policy_version": pack.policy_version,
                    "not_comprehensive_semantic_scan": True,
                },
                policy_version=pack.policy_version or ctx.policy.version,
            )
        if review_codes:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=review_codes,
                severity=ValidationSeverity.SAFETY,
                blocking=False,
                target={"safety_rules_version": pack.version},
                observed={"ambiguous_semantic": True, "policy_version": pack.policy_version},
                policy_version=pack.policy_version or ctx.policy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["SAFE-PASS"],
            severity=ValidationSeverity.SAFETY,
            blocking=False,
            target={"safety_rules_version": pack.version},
            observed={"clean": True, "policy_version": pack.policy_version},
            policy_version=pack.policy_version or ctx.policy.version,
        )
