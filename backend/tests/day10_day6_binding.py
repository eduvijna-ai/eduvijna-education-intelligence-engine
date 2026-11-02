from __future__ import annotations

from sqlalchemy.orm import Session

from app.education_intelligence.policy_registry import V1_POLICY_VERSION
from app.education_intelligence.taxonomy_registry import V1_TAXONOMY_VERSION
from app.models.education_intelligence import ValidationAuditRun


def seed_production_day6_audit(
    session: Session,
    *,
    item_id: str,
    organization_id: str | None = None,
    institution_id: str | None = None,
    curriculum_version_id: str | None = None,
    input_hash: str | None = None,
    learning_outcome_id: str | None = None,
    competency_codes: list[str] | None = None,
    declared_cognitive_level: str = "remember",
    grade_year_code: str = "grade-4",
    medium_code: str = "english",
    subject_code: str = "mathematics",
) -> tuple[str, dict[str, object]]:
    digest = input_hash or ("e" * 64)
    lo_id = learning_outcome_id or "00000000-0000-4000-8000-0000000000d6"
    competencies = competency_codes or ["knowledge"]
    validated = {
        "item_id": item_id,
        "input_hash": digest,
        "declared_cognitive_level": declared_cognitive_level,
        "learning_outcome_ids": [lo_id],
        "competency_codes": competencies,
        "institution_id": institution_id,
        "curriculum_version_id": curriculum_version_id,
        "grade_year_code": grade_year_code,
        "medium_code": medium_code,
        "subject_code": subject_code,
    }
    run = ValidationAuditRun(
        run_id=f"day6-{item_id}",
        input_hash=digest,
        taxonomy_version=V1_TAXONOMY_VERSION,
        policy_version=V1_POLICY_VERSION,
        aggregate_status="pass",
        blocking_failure=False,
        institution_id=institution_id,
        metadata_json={
            "kind": "day6_validation",
            "scope": {
                "organization_id": organization_id,
                "institution_id": institution_id,
                "curriculum_version_id": curriculum_version_id,
            },
            "validated_items": [validated],
        },
    )
    session.add(run)
    session.flush()
    return str(run.id), validated
