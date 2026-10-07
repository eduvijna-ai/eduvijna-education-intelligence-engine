from __future__ import annotations

from sqlalchemy.orm import Session

from app.education_intelligence.audit import persist_validation_run
from app.education_intelligence.composition import run_validation
from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import (
    CanonicalAssessmentItem,
    InstitutionPolicyOverride,
    ValidationRunSummary,
)
from app.education_intelligence.policy_registry import load_policy_registry
from app.education_intelligence.registry import ValidatorRegistry, build_default_registry
from app.education_intelligence.taxonomy_registry import seed_taxonomy_registry
from app.education_intelligence.validators.cognition import CognitiveProgressionValidator
from app.models.education_intelligence import ValidationAuditRun


class EducationIntelligenceValidationService:
    """Callable without FastAPI, RAG, or agents (D6-02, D6-30)."""

    def __init__(
        self,
        session: Session | None = None,
        registry: ValidatorRegistry | None = None,
    ) -> None:
        self.session = session
        self.registry = registry or build_default_registry()
        if session is not None:
            seed_taxonomy_registry(session)

    def validate_item(
        self,
        item: CanonicalAssessmentItem,
        *,
        curriculum_version_id: str | None = None,
        board_code: str | None = None,
        institution_overrides: list[InstitutionPolicyOverride] | None = None,
        validator_ids: list[str] | None = None,
        persist: bool = False,
        actor_id: str | None = None,
    ) -> ValidationRunSummary:
        ctx = ValidationContext.create(
            self.session,
            curriculum_version_id=curriculum_version_id or item.curriculum_version_id,
            board_code=board_code,
        )
        if institution_overrides:
            ctx.policy = load_policy_registry(self.session, institution_overrides)
        summary = run_validation(item, ctx, self.registry, validator_ids=validator_ids)
        if persist and self.session is not None:
            persist_validation_run(
                self.session,
                summary,
                institution_id=item.institution_id,
                actor_id=actor_id,
            )
            self.session.commit()
        return summary

    def validate_cognitive_progression(
        self, progression: list[str], board_code: str | None = None
    ) -> ValidationRunSummary:
        ctx = ValidationContext.create(self.session, board_code=board_code)
        validator = CognitiveProgressionValidator()
        result = validator.validate_progression(progression, ctx)
        dummy = CanonicalAssessmentItem(
            item_id="progression-only",
            stem_text="progression-check",
            cognitive_progression=progression,
        )
        from uuid import uuid4

        from app.education_intelligence.composition import aggregate_status, bind_provenance
        from app.education_intelligence.explain import explain_results

        results = bind_provenance(
            [result],
            item=dummy,
            taxonomy_version=ctx.taxonomy.version,
            policy_version=ctx.policy.version,
        )
        return ValidationRunSummary(
            run_id=str(uuid4()),
            input_hash=dummy.canonical_hash(),
            aggregate_status=aggregate_status(results),
            blocking_failure=result.blocking and result.status.value == "fail",
            results=results,
            taxonomy_version=ctx.taxonomy.version,
            policy_version=ctx.policy.version,
            validator_versions={validator.validator_id: validator.validator_version},
            explanations=explain_results(results),
        )

    def get_audit_run(self, run_id: str) -> ValidationAuditRun | None:
        if self.session is None:
            return None
        from sqlalchemy import select

        return self.session.scalar(
            select(ValidationAuditRun).where(ValidationAuditRun.run_id == run_id)
        )
