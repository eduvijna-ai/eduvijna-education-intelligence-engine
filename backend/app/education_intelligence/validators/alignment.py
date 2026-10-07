from __future__ import annotations

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    EvidenceRef,
    ValidationResult,
)
from app.education_intelligence.enums import EvidenceAuthority, ValidationSeverity, ValidationStatus
from app.models.curriculum import CurriculumVersion
from app.models.enums import CurriculumStatus


class LearningOutcomeValidator:
    validator_id = "learning_outcome_alignment"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        if not item.learning_outcome_ids:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.NOT_APPLICABLE,
                rule_codes=["LO-ALIGN-000"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"learning_outcome_ids": []},
                observed={},
                taxonomy_version=ctx.taxonomy.version,
            )
        if not item.curriculum_version_id:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["LO-ALIGN-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"learning_outcome_ids": item.learning_outcome_ids},
                observed={"curriculum_version_id": None},
                taxonomy_version=ctx.taxonomy.version,
            )
        if ctx.session is None or ctx.curriculum_index is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["LO-ALIGN-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"learning_outcome_ids": item.learning_outcome_ids},
                observed={"reason": "curriculum_index_unavailable"},
                taxonomy_version=ctx.taxonomy.version,
            )
        version = ctx.session.get(CurriculumVersion, item.curriculum_version_id)
        if version is None or version.status != CurriculumStatus.ACTIVE.value:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["LO-ALIGN-003"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"curriculum_version_id": item.curriculum_version_id},
                observed={"status": getattr(version, "status", None)},
                taxonomy_version=ctx.taxonomy.version,
            )
        missing: list[str] = []
        inactive: list[str] = []
        wrong_scope: list[str] = []
        evidence: list[EvidenceRef] = []
        for lo_id in item.learning_outcome_ids:
            lo = ctx.curriculum_index.learning_outcomes.get(lo_id)
            if lo is None:
                missing.append(lo_id)
                continue
            if not lo.active:
                inactive.append(lo_id)
            if lo.curriculum_version_id != item.curriculum_version_id:
                wrong_scope.append(lo_id)
            if lo.source_revision_id:
                evidence.append(
                    EvidenceRef(
                        authority=EvidenceAuthority.OFFICIAL_CURRICULUM_RULE,
                        entity_type="learning_outcome",
                        entity_id=lo.id,
                        source_revision_id=lo.source_revision_id,
                        locator=lo.source_locator,
                    )
                )
        if missing or inactive or wrong_scope:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["LO-ALIGN-004"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={
                    "learning_outcome_ids": item.learning_outcome_ids,
                    "grade_year_code": item.grade_year_code,
                    "subject_code": item.subject_code,
                    "medium_code": item.medium_code,
                },
                observed={
                    "missing": missing,
                    "inactive": inactive,
                    "wrong_scope": wrong_scope,
                },
                evidence=evidence,
                taxonomy_version=ctx.taxonomy.version,
            )
        scope_ok = True
        if item.subject_code and item.subject_code not in ctx.curriculum_index.nodes_by_code:
            scope_ok = False
        if not scope_ok:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["LO-ALIGN-005"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"subject_code": item.subject_code},
                observed={"resolved_subject": False},
                evidence=evidence,
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["LO-ALIGN-006"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"learning_outcome_ids": item.learning_outcome_ids},
            observed={"aligned": True},
            evidence=evidence,
            taxonomy_version=ctx.taxonomy.version,
        )


class SourceBackedCompetencyValidator:
    validator_id = "source_backed_competency"
    validator_version = "1.0.0"

    def validate(self, item: CanonicalAssessmentItem, ctx: ValidationContext) -> ValidationResult:
        if not item.competency_claim_official:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.NOT_APPLICABLE,
                rule_codes=["COMP-SRC-000"],
                severity=ValidationSeverity.ADVISORY,
                blocking=False,
                target={"competency_claim_official": False},
                observed={"generic_tagging": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        if ctx.curriculum_index is None:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["COMP-SRC-001"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"competency_codes": item.competency_codes},
                observed={"evidence": "unavailable"},
                taxonomy_version=ctx.taxonomy.version,
            )
        unresolved: list[str] = []
        evidence: list[EvidenceRef] = []
        for raw in item.competency_codes:
            code, _ = ctx.taxonomy.resolve_competency(raw)
            if code is None:
                unresolved.append(raw)
                continue
            comp = ctx.curriculum_index.competencies_by_code.get(code)
            if comp is None or not comp.source_revision_id:
                unresolved.append(code)
            elif comp.source_revision_id:
                evidence.append(
                    EvidenceRef(
                        authority=EvidenceAuthority.OFFICIAL_CURRICULUM_RULE,
                        entity_type="competency",
                        entity_id=comp.id,
                        source_revision_id=comp.source_revision_id,
                        locator=comp.source_locator,
                    )
                )
        if unresolved:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COMP-SRC-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={"competency_codes": item.competency_codes},
                observed={"unresolved_official": unresolved},
                evidence=evidence,
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["COMP-SRC-003"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={"competency_codes": item.competency_codes},
            observed={"official_mapping": True},
            evidence=evidence,
            taxonomy_version=ctx.taxonomy.version,
        )
