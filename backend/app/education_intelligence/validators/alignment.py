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


def _entity_refs(evidence: list[EvidenceRef]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for ev in evidence:
        refs.append(
            {
                "entity_type": ev.entity_type,
                "entity_id": ev.entity_id or "",
                "source_revision_id": ev.source_revision_id or "",
            }
        )
    return refs


class LearningOutcomeValidator:
    validator_id = "learning_outcome_alignment"
    validator_version = "1.1.0"

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
        if not item.grade_year_code or not item.subject_code:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["LO-ALIGN-007"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={
                    "grade_year_code": item.grade_year_code,
                    "subject_code": item.subject_code,
                    "medium_code": item.medium_code,
                },
                observed={"scope_claims_incomplete": True},
                taxonomy_version=ctx.taxonomy.version,
            )
        missing: list[str] = []
        inactive: list[str] = []
        wrong_version: list[str] = []
        scope_failures: list[dict[str, str]] = []
        missing_source: list[str] = []
        evidence: list[EvidenceRef] = []
        for lo_id in item.learning_outcome_ids:
            lo = ctx.curriculum_index.learning_outcomes.get(lo_id)
            if lo is None:
                missing.append(lo_id)
                continue
            if not lo.active:
                inactive.append(lo_id)
            if lo.curriculum_version_id != item.curriculum_version_id:
                wrong_version.append(lo_id)
            matched, reason = ctx.curriculum_index.lo_matches_claim(
                lo_id,
                grade_year_code=item.grade_year_code,
                medium_code=item.medium_code,
                subject_code=item.subject_code,
            )
            if not matched:
                scope_failures.append({"lo_id": lo_id, "reason": reason or "scope_mismatch"})
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
            else:
                missing_source.append(lo_id)
        if missing or inactive or wrong_version or scope_failures:
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
                    "wrong_version": wrong_version,
                    "scope_failures": scope_failures,
                },
                evidence=evidence,
                source_entity_refs=_entity_refs(evidence),
                taxonomy_version=ctx.taxonomy.version,
            )
        if missing_source:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["LO-ALIGN-008"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"learning_outcome_ids": item.learning_outcome_ids},
                observed={"missing_source_revision": missing_source},
                evidence=evidence,
                source_entity_refs=_entity_refs(evidence),
                taxonomy_version=ctx.taxonomy.version,
            )
        return ValidationResult(
            validator_id=self.validator_id,
            validator_version=self.validator_version,
            status=ValidationStatus.PASS,
            rule_codes=["LO-ALIGN-006"],
            severity=ValidationSeverity.MANDATORY,
            blocking=False,
            target={
                "learning_outcome_ids": item.learning_outcome_ids,
                "grade_year_code": item.grade_year_code,
                "subject_code": item.subject_code,
                "medium_code": item.medium_code,
            },
            observed={"exact_scope_aligned": True},
            evidence=evidence,
            source_entity_refs=_entity_refs(evidence),
            taxonomy_version=ctx.taxonomy.version,
        )


class SourceBackedCompetencyValidator:
    validator_id = "source_backed_competency"
    validator_version = "1.1.0"

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
        if ctx.curriculum_index is None or not item.curriculum_version_id:
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
        wrong_scope: list[str] = []
        missing_source: list[str] = []
        evidence: list[EvidenceRef] = []
        for raw in item.competency_codes:
            code, _ = ctx.taxonomy.resolve_competency(raw)
            if code is None:
                unresolved.append(raw)
                continue
            comp = next(
                (
                    c
                    for c in ctx.curriculum_index.competencies_by_id.values()
                    if c.code == code
                ),
                None,
            )
            if comp is None:
                unresolved.append(code)
                continue
            if not ctx.curriculum_index.competency_in_scope(
                comp.id,
                framework_id=ctx.curriculum_index.framework_id,
                curriculum_version_id=item.curriculum_version_id,
            ):
                wrong_scope.append(code)
                continue
            scopes = ctx.curriculum_index.competency_scopes.get(comp.id, [])
            if scopes and item.subject_code:
                if not any(
                    s.subject_code is None or s.subject_code == item.subject_code for s in scopes
                ):
                    wrong_scope.append(code)
                    continue
            if not comp.source_revision_id:
                missing_source.append(code)
                continue
            evidence.append(
                EvidenceRef(
                    authority=EvidenceAuthority.OFFICIAL_CURRICULUM_RULE,
                    entity_type="competency",
                    entity_id=comp.id,
                    source_revision_id=comp.source_revision_id,
                    locator=comp.source_locator,
                )
            )
        if unresolved or wrong_scope:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.FAIL,
                rule_codes=["COMP-SRC-002"],
                severity=ValidationSeverity.MANDATORY,
                blocking=True,
                target={
                    "competency_codes": item.competency_codes,
                    "curriculum_version_id": item.curriculum_version_id,
                    "subject_code": item.subject_code,
                },
                observed={"unresolved": unresolved, "wrong_scope": wrong_scope},
                evidence=evidence,
                source_entity_refs=_entity_refs(evidence),
                taxonomy_version=ctx.taxonomy.version,
            )
        if missing_source:
            return ValidationResult(
                validator_id=self.validator_id,
                validator_version=self.validator_version,
                status=ValidationStatus.REVIEW_REQUIRED,
                rule_codes=["COMP-SRC-004"],
                severity=ValidationSeverity.MANDATORY,
                blocking=False,
                target={"competency_codes": item.competency_codes},
                observed={"missing_source_revision": missing_source},
                evidence=evidence,
                source_entity_refs=_entity_refs(evidence),
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
            observed={"official_scope_mapping": True},
            evidence=evidence,
            source_entity_refs=_entity_refs(evidence),
            taxonomy_version=ctx.taxonomy.version,
        )
