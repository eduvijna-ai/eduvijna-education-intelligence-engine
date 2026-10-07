from __future__ import annotations

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import CanonicalAssessmentItem, ValidationResult
from app.education_intelligence.enums import ValidationSeverity, ValidationStatus


class CognitiveTaxonomyValidator:
    validator_id = "cognitive_taxonomy"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        raw = item.declared_cognitive_level
        if not raw:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["COG-TAX-001"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"field": "declared_cognitive_level"},
                observed={"value": None},
                taxonomy_version=ctx.taxonomy.version,
            )
        resolved, via_alias = ctx.taxonomy.resolve_cognitive(raw)
        if resolved is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COG-TAX-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"declared": raw},
                observed={"resolved": None},
                taxonomy_version=ctx.taxonomy.version,
            )
        status = ValidationStatus.PASS
        rule_codes = ["COG-TAX-003"]
        if via_alias:
            status = ValidationStatus.REVIEW_REQUIRED
            rule_codes.append("COG-TAX-004")
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=status,
            rule_codes=rule_codes,
            severity=ValidationSeverity.MANDATORY,
            blocking=status == ValidationStatus.FAIL,
            target={"declared": raw},
            observed={"resolved": resolved, "via_alias": via_alias},
            taxonomy_version=ctx.taxonomy.version,
        )


class CompetencyTaxonomyValidator:
    validator_id = "competency_taxonomy"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        if not item.competency_codes:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["COMP-TAX-001"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"competency_codes": []},
                observed={"resolved": []},
                taxonomy_version=ctx.taxonomy.version,
            )
        resolved: list[str] = []
        unknown: list[str] = []
        alias_hits: list[str] = []
        for raw in item.competency_codes:
            code, via_alias = ctx.taxonomy.resolve_competency(raw)
            if code is None:
                unknown.append(raw)
            else:
                resolved.append(code)
                if via_alias:
                    alias_hits.append(raw)
        duplicates = len(resolved) != len(set(resolved))
        if unknown:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COMP-TAX-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"competency_codes": item.competency_codes},
                observed={"unknown": unknown, "resolved": resolved},
                taxonomy_version=ctx.taxonomy.version,
            )
        if duplicates:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COMP-TAX-003"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"competency_codes": item.competency_codes},
                observed={"resolved": resolved, "duplicate": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        status = ValidationStatus.PASS
        rules = ["COMP-TAX-004"]
        if alias_hits:
            status = ValidationStatus.REVIEW_REQUIRED
            rules.append("COMP-TAX-005")
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=status,
            rule_codes=rules,
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"competency_codes": item.competency_codes},
            observed={"resolved": sorted(set(resolved)), "alias_hits": alias_hits},
            taxonomy_version=ctx.taxonomy.version,
        )
