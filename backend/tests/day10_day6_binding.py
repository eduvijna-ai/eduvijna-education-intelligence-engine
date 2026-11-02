from __future__ import annotations

from sqlalchemy.orm import Session

from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
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
) -> tuple[str, dict[str, object]]:
    digest = input_hash or ("e" * 64)
    lo_id = learning_outcome_id or "00000000-0000-4000-8000-0000000000d6"
    competencies = competency_codes or ["knowledge"]
    run = ValidationAuditRun(
        run_id=f"day6-{item_id}",
        input_hash=digest,
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        policy_version="cbse-primary@v1",
        aggregate_status="pass",
        blocking_failure=False,
        institution_id=institution_id,
        metadata_json={
            "scope": {
                "organization_id": organization_id,
                "institution_id": institution_id,
                "curriculum_version_id": curriculum_version_id,
            },
            "validated_items": [
                {
                    "item_id": item_id,
                    "input_hash": digest,
                    "learning_outcome_id": lo_id,
                    "competency_codes": competencies,
                    "grade_year_code": "grade-4",
                    "medium_code": "english",
                    "subject_code": "mathematics",
                }
            ],
        },
    )
    session.add(run)
    session.flush()
    return str(run.id), {
        "input_hash": digest,
        "learning_outcome_ids": [lo_id],
        "competency_codes": competencies,
    }
