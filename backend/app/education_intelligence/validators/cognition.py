from __future__ import annotations

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    CognitiveDemandEvidence,
    ValidationResult,
    infer_observed_cognitive_level,
)
from app.education_intelligence.enums import ValidationSeverity, ValidationStatus
from app.education_intelligence.taxonomy_registry import COGNITIVE_PROGRESSION_ORDER


class CognitiveDemandEvidenceValidator:
    validator_id = "cognitive_demand_evidence"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        evidence = item.cognitive_demand_evidence
        if evidence is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["COG-EVID-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"cognitive_demand_evidence": None},
                observed={"self_attested_label_only": bool(item.declared_cognitive_level)},
                taxonomy_version=ctx.taxonomy.version,
            )
        if not _has_any_signal(evidence):
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COG-EVID-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"cognitive_demand_evidence": evidence.model_dump()},
                observed={"signals_present": False},
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["COG-EVID-003"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"cognitive_demand_evidence": evidence.model_dump()},
            observed={"signals_present": True},
            taxonomy_version=ctx.taxonomy.version,
        )


def _has_any_signal(evidence: CognitiveDemandEvidence) -> bool:
    return any(
        [
            evidence.recall_required,
            evidence.interpretation_required,
            evidence.application_required,
            evidence.multi_step_reasoning,
            evidence.comparison_or_evaluation,
            evidence.justification_required,
        ]
    )


class TargetObservedCognitiveValidator:
    validator_id = "target_observed_cognitive"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        declared = item.declared_cognitive_level
        evidence = item.cognitive_demand_evidence
        if not declared:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.NOT_APPLICABLE,
                rule_codes=["COG-TGT-000"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={},
                observed={},
                taxonomy_version=ctx.taxonomy.version,
            )
        declared_code, _ = ctx.taxonomy.resolve_cognitive(declared)
        if declared_code is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COG-TGT-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"declared": declared},
                observed={"resolved": None},
                taxonomy_version=ctx.taxonomy.version,
            )
        if evidence is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["COG-TGT-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"declared": declared_code},
                observed={"observed": None, "reason": "missing_evidence"},
                taxonomy_version=ctx.taxonomy.version,
            )
        observed_code, uncertain = infer_observed_cognitive_level(evidence)
        if uncertain or observed_code is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["COG-TGT-003"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"declared": declared_code},
                observed={"observed": observed_code, "uncertain": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        declared_idx = ctx.taxonomy.cognitive_order_index(declared_code) or 0
        observed_idx = ctx.taxonomy.cognitive_order_index(observed_code) or 0
        delta = observed_idx - declared_idx
        if delta >= 2 or delta <= -2:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COG-TGT-004"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"declared": declared_code},
                observed={"observed": observed_code, "delta_levels": delta},
                taxonomy_version=ctx.taxonomy.version,
            )
        if delta != 0:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.WARN,
                rule_codes=["COG-TGT-005"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"declared": declared_code},
                observed={"observed": observed_code, "delta_levels": delta},
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["COG-TGT-006"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"declared": declared_code},
            observed={"observed": observed_code},
            taxonomy_version=ctx.taxonomy.version,
        )


class CognitiveProgressionValidator:
    """D6-11: explicit progression only — no paper distribution."""

    validator_id = "cognitive_progression"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        progression = item.cognitive_progression
        if not progression:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.NOT_APPLICABLE,
                rule_codes=["COG-PROG-000"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"cognitive_progression": []},
                observed={},
                taxonomy_version=ctx.taxonomy.version,
            )
        return self.validate_progression(progression, ctx)

    def validate_progression(
        self, progression: list[str], ctx: ValidationContext
    ) -> ValidationResult:
        resolved: list[str] = []
        unknown: list[str] = []
        for raw in progression:
            code, _ = ctx.taxonomy.resolve_cognitive(raw)
            if code is None:
                unknown.append(raw)
            else:
                resolved.append(code)
        if unknown:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COG-PROG-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"progression": progression},
                observed={"unknown": unknown},
                taxonomy_version=ctx.taxonomy.version,
            )
        order_map = {c: i for i, c in enumerate(COGNITIVE_PROGRESSION_ORDER)}
        last = -1
        for code in resolved:
            idx = order_map.get(code, -1)
            if idx < last:
                return ValidationResult(
                    validator_id=self.validator_id,
                    validator_version=self.validator_version,
                    status=ValidationStatus.FAIL,
                    rule_codes=["COG-PROG-002"],
                    severity=ValidationSeverity.MANDATORY,
                    blocking=True,
                    target={"progression": progression},
                    observed={"resolved": resolved, "invalid_order": True},
                    taxonomy_version=ctx.taxonomy.version,
                )
            last = idx
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["COG-PROG-003"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"progression": progression},
            observed={"resolved": resolved},
            taxonomy_version=ctx.taxonomy.version,
        )
