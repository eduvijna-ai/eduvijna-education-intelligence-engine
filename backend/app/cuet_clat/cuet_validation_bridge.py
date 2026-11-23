"""Day6 validation + independent solver evidence binding for CUET persisted questions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cuet_clat.cuet_canonical_mapping import question_to_canonical_assessment_item
from app.cuet_clat.cuet_math_solver import CuetSolverEvidence
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.jee_advanced.question_fingerprint import question_content_fingerprint
from app.models import Question, ValidationAuditRun


def attach_independent_solver_evidence(
    session: Session,
    *,
    run_id: str,
    question: Question,
    evidence: CuetSolverEvidence,
) -> None:
    record = session.scalar(select(ValidationAuditRun).where(ValidationAuditRun.run_id == run_id))
    if record is None:
        msg = f"missing validation run {run_id}"
        raise RuntimeError(msg)
    rows = [dict(row) for row in (record.results_json or []) if isinstance(row, dict)]
    rows.append(
        {
            "kind": "independent_solver",
            "evidence_id": evidence.evidence_id,
            "item_id": str(question.id),
            "steps": list(evidence.steps),
            "derived_answer_key": evidence.answer_key,
        }
    )
    record.results_json = rows
    meta = dict(question.metadata_json or {})
    meta["day6_solver_evidence_id"] = evidence.evidence_id
    meta["day6_solver_steps"] = list(evidence.steps)
    question.metadata_json = meta
    session.flush()


def run_day6_validation_for_question(
    session: Session,
    *,
    question: Question,
    curriculum_version_id: str,
    learning_outcome_id: str,
    competency_code: str,
    organization_id: str,
    institution_id: str,
    evidence: CuetSolverEvidence,
) -> tuple[bool, str | None]:
    service = EducationIntelligenceValidationService(session)
    canonical = question_to_canonical_assessment_item(
        question,
        curriculum_version_id=curriculum_version_id,
        learning_outcome_id=learning_outcome_id,
        competency_code=competency_code,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    summary = service.validate_item(
        canonical,
        curriculum_version_id=curriculum_version_id,
        board_code="cbse",
        persist=True,
        actor_id="d13-cuet-synthetic-author",
        trusted_scope={
            "organization_id": organization_id,
            "institution_id": institution_id,
            "curriculum_version_id": curriculum_version_id,
        },
    )
    if summary.blocking_failure or summary.aggregate_status != ValidationStatus.PASS:
        return False, "day6_validation_not_pass"

    content_fp = question_content_fingerprint(question)
    canonical_fp = summary.input_hash
    meta = dict(question.metadata_json or {})
    meta["day6_validation_audit_id"] = summary.run_id
    meta["day6_canonical_input_hash"] = canonical_fp
    meta["day6_content_fingerprint"] = content_fp
    question.metadata_json = meta
    session.flush()

    attach_independent_solver_evidence(
        session,
        run_id=summary.run_id,
        question=question,
        evidence=evidence,
    )
    return True, None


def persisted_validation_covers_question(
    session: Session,
    *,
    question: Question,
    organization_id: str,
    institution_id: str,
) -> tuple[bool, str | None]:
    """Verify real Day6 audit + content fingerprint + solver evidence."""

    meta = dict(question.metadata_json or {})
    run_id = str(meta.get("day6_validation_audit_id") or "").strip()
    if not run_id:
        return False, "missing_validation_run"
    if str(meta.get("organization_id") or "") != organization_id.strip():
        return False, "organization_mismatch"
    if institution_id and str(meta.get("institution_id") or "") != institution_id.strip():
        return False, "institution_mismatch"

    record = session.scalar(select(ValidationAuditRun).where(ValidationAuditRun.run_id == run_id))
    if record is None:
        return False, "validation_record_missing"
    if record.blocking_failure:
        return False, "blocking_validation_failure"
    if record.aggregate_status != ValidationStatus.PASS.value:
        return False, "validation_not_pass"

    canonical_fp = str(meta.get("day6_canonical_input_hash") or "")
    if record.input_hash != canonical_fp:
        return False, "canonical_hash_mismatch"

    if question_content_fingerprint(question) != str(meta.get("day6_content_fingerprint") or ""):
        return False, "content_fingerprint_stale"

    solver_id = str(meta.get("day6_solver_evidence_id") or "")
    proven = False
    for row in record.results_json or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "") != "independent_solver":
            continue
        if str(row.get("evidence_id") or "") != solver_id:
            continue
        if str(row.get("item_id") or "") == str(question.id):
            proven = True
            break
    if not proven:
        return False, "independent_solver_not_proven"
    if meta.get("day9_veto") is True:
        return False, "day9_veto"
    return True, None