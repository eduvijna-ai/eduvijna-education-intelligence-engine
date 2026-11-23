"""Day6 validation + independent solver evidence binding for CUET persisted questions."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cuet_clat.constants import CUET_MARK_CORRECT, CUET_MARK_INCORRECT
from app.cuet_clat.cuet_canonical_mapping import question_to_canonical_assessment_item
from app.cuet_clat.cuet_math_author import CuetMathAuthoredItem
from app.cuet_clat.cuet_math_solver import CuetSolverEvidence, solve_persisted_question
from app.education_intelligence.audit import persist_validation_run
from app.education_intelligence.context import ValidationContext
from app.education_intelligence.enums import ValidationStatus
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.jee_advanced.question_fingerprint import question_content_fingerprint
from app.models import Question, ValidationAuditRun


def _binding_payload(
    question: Question,
    *,
    curriculum_version_id: str,
    learning_outcome_id: str,
    competency_code: str,
    organization_id: str,
    institution_id: str,
    academic_year: str,
    medium_code: str,
    subject_code: str,
    topic_code: str,
    exam_version_id: str,
    content_fingerprint: str,
    canonical_input_hash: str,
    solver_derived_key: str,
    taxonomy_version: str,
    policy_version: str,
    run_id: str,
    validator_versions: dict[str, str] | None = None,
    quality_rule_pack_version: str | None = None,
    safety_rules_version: str | None = None,
) -> dict[str, object]:
    return {
        "organization_id": organization_id,
        "institution_id": institution_id,
        "academic_year": academic_year,
        "medium_code": medium_code,
        "subject_code": subject_code,
        "topic_code": topic_code,
        "marks_correct": CUET_MARK_CORRECT,
        "marks_incorrect": CUET_MARK_INCORRECT,
        "exam_version_id": exam_version_id,
        "curriculum_version_id": curriculum_version_id,
        "learning_outcome_id": learning_outcome_id,
        "competency_code": competency_code,
        "content_fingerprint": content_fingerprint,
        "canonical_input_hash": canonical_input_hash,
        "solver_derived_key": solver_derived_key,
        "day6_taxonomy_version": taxonomy_version,
        "day6_policy_version": policy_version,
        "day6_validation_run_id": run_id,
        "day6_validator_versions": dict(validator_versions or {}),
        "day6_quality_rule_pack_version": quality_rule_pack_version,
        "day6_safety_rules_version": safety_rules_version,
        "stem_text": question.stem_text,
        "answer_option_key": (question.answer_json or {}).get("option_key"),
        "option_keys": sorted(o.option_key for o in question.options),
        "option_text_by_key": {o.option_key: o.text for o in question.options},
    }


def _binding_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def authored_item_content_fingerprint(item: CuetMathAuthoredItem) -> str:
    payload = {
        "external_code": item.external_code,
        "stem_text": item.stem_text,
        "option_text_by_key": dict(sorted(item.option_text_by_key.items())),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _active_day6_provenance(
    session: Session,
    *,
    curriculum_version_id: str,
) -> ValidationContext:
    return ValidationContext.create(
        session,
        curriculum_version_id=curriculum_version_id,
        board_code="cbse",
    )


def audit_matches_active_day6_provenance(
    session: Session,
    record: ValidationAuditRun,
    binding: dict[str, object],
) -> tuple[bool, str | None]:
    curriculum_version_id = str(binding.get("curriculum_version_id") or "")
    if not curriculum_version_id:
        return False, "missing_curriculum_version"
    ctx = _active_day6_provenance(session, curriculum_version_id=curriculum_version_id)
    if record.taxonomy_version != ctx.taxonomy.version:
        return False, "taxonomy_superseded"
    if record.policy_version != ctx.policy.version:
        return False, "policy_superseded"
    record_meta = dict(record.metadata_json or {})
    quality = record_meta.get("quality_rule_pack_version")
    if ctx.quality_rule_pack and quality != ctx.quality_rule_pack.version:
        return False, "quality_pack_superseded"
    safety = record_meta.get("safety_rules_version")
    if ctx.safety_rule_pack and safety != ctx.safety_rule_pack.version:
        return False, "safety_rules_superseded"
    if str(binding.get("day6_taxonomy_version") or "") != ctx.taxonomy.version:
        return False, "binding_taxonomy_stale"
    if str(binding.get("day6_policy_version") or "") != ctx.policy.version:
        return False, "binding_policy_stale"
    bound_quality = binding.get("day6_quality_rule_pack_version")
    if ctx.quality_rule_pack:
        if bound_quality not in (None, "") and bound_quality != ctx.quality_rule_pack.version:
            return False, "binding_quality_stale"
    bound_safety = binding.get("day6_safety_rules_version")
    if ctx.safety_rule_pack:
        if bound_safety not in (None, "") and bound_safety != ctx.safety_rule_pack.version:
            return False, "binding_safety_stale"
    raw_bound = binding.get("day6_validator_versions")
    if isinstance(raw_bound, dict) and raw_bound:
        stored_validators = dict(record_meta.get("validator_versions") or {})
        bound_validators = {str(k): str(v) for k, v in raw_bound.items()}
        if stored_validators != bound_validators:
            return False, "validator_versions_mismatch"
    return True, None


def validate_mcq_integrity(question: Question) -> tuple[bool, str | None]:
    if not (question.stem_text or "").strip():
        return False, "blank_stem"
    if len(question.options) != 4:
        return False, "option_count"
    keys = [opt.option_key for opt in question.options]
    texts = [opt.text.strip() for opt in question.options]
    if len(set(keys)) != 4:
        return False, "duplicate_keys"
    if any(not text for text in texts):
        return False, "blank_option"
    if len(set(texts)) != 4:
        return False, "duplicate_option_text"
    correct = [opt for opt in question.options if opt.is_correct]
    if len(correct) != 1:
        return False, "correct_count"
    declared = (question.answer_json or {}).get("option_key")
    if declared != correct[0].option_key:
        return False, "answer_json_mismatch"
    return True, None


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
    meta["day6_solver_derived_key"] = evidence.answer_key
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
    academic_year: str,
    medium_code: str,
    subject_code: str,
    topic_code: str,
    exam_version_id: str,
) -> tuple[bool, str | None]:
    ok_mcq, reason = validate_mcq_integrity(question)
    if not ok_mcq:
        return False, reason

    service = EducationIntelligenceValidationService(session)
    canonical = question_to_canonical_assessment_item(
        question,
        curriculum_version_id=curriculum_version_id,
        learning_outcome_id=learning_outcome_id,
        competency_code=competency_code,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    recomputed_canonical_hash = canonical.canonical_hash()
    summary = service.validate_item(
        canonical,
        curriculum_version_id=curriculum_version_id,
        board_code="cbse",
        persist=False,
        actor_id="d13-cuet-synthetic-author",
        trusted_scope={
            "organization_id": organization_id,
            "institution_id": institution_id,
            "curriculum_version_id": curriculum_version_id,
        },
    )
    if summary.blocking_failure or summary.aggregate_status != ValidationStatus.PASS:
        return False, "day6_validation_not_pass"
    if summary.input_hash != recomputed_canonical_hash:
        return False, "canonical_hash_mismatch_at_validation"

    record = persist_validation_run(
        session,
        summary,
        institution_id=institution_id,
        actor_id="d13-cuet-synthetic-author",
    )

    content_fp = question_content_fingerprint(question)
    binding_payload = _binding_payload(
        question,
        curriculum_version_id=curriculum_version_id,
        learning_outcome_id=learning_outcome_id,
        competency_code=competency_code,
        organization_id=organization_id,
        institution_id=institution_id,
        academic_year=academic_year,
        medium_code=medium_code,
        subject_code=subject_code,
        topic_code=topic_code,
        exam_version_id=exam_version_id,
        content_fingerprint=content_fp,
        canonical_input_hash=record.input_hash,
        solver_derived_key=evidence.answer_key,
        taxonomy_version=record.taxonomy_version,
        policy_version=record.policy_version,
        run_id=record.run_id,
        validator_versions=summary.validator_versions,
        quality_rule_pack_version=str(summary.metadata.get("quality_rule_pack_version") or ""),
        safety_rules_version=str(summary.metadata.get("safety_rules_version") or ""),
    )
    meta = dict(question.metadata_json or {})
    meta["day6_validation_audit_id"] = summary.run_id
    meta["day6_canonical_input_hash"] = record.input_hash
    meta["day6_content_fingerprint"] = content_fp
    binding_hash = _binding_hash(binding_payload)
    meta["d13_issuance_binding"] = {**binding_payload, "binding_hash": binding_hash}
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
    """Recompute Day6 canonical hash, issuance binding, and independent solver proof."""

    meta = dict(question.metadata_json or {})
    binding = meta.get("d13_issuance_binding")
    if not isinstance(binding, dict):
        return False, "missing_issuance_binding"

    run_id = str(
        binding.get("day6_validation_run_id") or meta.get("day6_validation_audit_id") or ""
    )
    if not run_id:
        return False, "missing_validation_run"

    def _scope_mismatch(field: str, current: object, bound: object) -> bool:
        return str(current or "").strip() != str(bound or "").strip()

    bound_org = binding.get("organization_id")
    if _scope_mismatch("organization_id", meta.get("organization_id"), bound_org):
        return False, "organization_mismatch"
    if organization_id and _scope_mismatch("organization_id", organization_id, bound_org):
        return False, "organization_mismatch"
    bound_inst = binding.get("institution_id")
    if institution_id and _scope_mismatch("institution_id", meta.get("institution_id"), bound_inst):
        return False, "institution_mismatch"
    if _scope_mismatch("medium_code", meta.get("medium_code"), binding.get("medium_code")):
        return False, "medium_mismatch"
    if _scope_mismatch("subject_code", meta.get("subject_code"), binding.get("subject_code")):
        return False, "subject_mismatch"
    if _scope_mismatch("topic_code", meta.get("topic_code"), binding.get("topic_code")):
        return False, "topic_mismatch"
    if _scope_mismatch("academic_year", meta.get("academic_year"), binding.get("academic_year")):
        return False, "year_mismatch"
    if float(meta.get("marks_correct") or 0) != float(binding.get("marks_correct") or -99):
        return False, "marks_mismatch"
    if float(meta.get("marks_incorrect") or 0) != float(binding.get("marks_incorrect") or -99):
        return False, "marks_mismatch"
    if str(question.exam_version_id) != str(binding.get("exam_version_id") or ""):
        return False, "exam_version_mismatch"

    ok_mcq, reason = validate_mcq_integrity(question)
    if not ok_mcq:
        return False, reason

    record = session.scalar(select(ValidationAuditRun).where(ValidationAuditRun.run_id == run_id))
    if record is None:
        return False, "validation_record_missing"
    if record.blocking_failure:
        return False, "blocking_validation_failure"
    if record.aggregate_status != ValidationStatus.PASS.value:
        return False, "validation_not_pass"
    if record.institution_id and institution_id and record.institution_id != institution_id:
        return False, "audit_institution_mismatch"
    scope = dict((record.metadata_json or {}).get("scope") or {})
    if scope.get("organization_id") and scope.get("organization_id") != organization_id:
        return False, "audit_org_mismatch"
    ok_active, active_reason = audit_matches_active_day6_provenance(session, record, binding)
    if not ok_active:
        return False, active_reason

    canonical = question_to_canonical_assessment_item(
        question,
        curriculum_version_id=str(binding.get("curriculum_version_id") or ""),
        learning_outcome_id=str(binding.get("learning_outcome_id") or ""),
        competency_code=str(binding.get("competency_code") or ""),
        organization_id=organization_id,
        institution_id=institution_id,
    )
    if record.input_hash != canonical.canonical_hash():
        return False, "canonical_hash_stale"

    content_fp = question_content_fingerprint(question)
    if content_fp != str(binding.get("content_fingerprint") or ""):
        return False, "content_fingerprint_stale"

    rebound = _binding_payload(
        question,
        curriculum_version_id=str(binding.get("curriculum_version_id") or ""),
        learning_outcome_id=str(binding.get("learning_outcome_id") or ""),
        competency_code=str(binding.get("competency_code") or ""),
        organization_id=organization_id,
        institution_id=institution_id,
        academic_year=str(binding.get("academic_year") or ""),
        medium_code=str(meta.get("medium_code") or ""),
        subject_code=str(meta.get("subject_code") or ""),
        topic_code=str(meta.get("topic_code") or ""),
        exam_version_id=str(question.exam_version_id),
        content_fingerprint=content_fp,
        canonical_input_hash=canonical.canonical_hash(),
        solver_derived_key=str(binding.get("solver_derived_key") or ""),
        taxonomy_version=record.taxonomy_version,
        policy_version=record.policy_version,
        run_id=run_id,
        validator_versions=dict(binding.get("day6_validator_versions") or {}),
        quality_rule_pack_version=str(binding.get("day6_quality_rule_pack_version") or ""),
        safety_rules_version=str(binding.get("day6_safety_rules_version") or ""),
    )
    if _binding_hash(rebound) != str(binding.get("binding_hash") or ""):
        return False, "issuance_binding_stale"

    evidence = solve_persisted_question(question)
    if evidence is None:
        return False, "solver_recompute_failed"
    bound_solver_key = str(binding.get("solver_derived_key") or "")
    if evidence.answer_key != bound_solver_key:
        return False, "solver_binding_mismatch"
    declared = (question.answer_json or {}).get("option_key")
    if evidence.answer_key != declared:
        return False, "solver_answer_json_mismatch"

    solver_id = str(meta.get("day6_solver_evidence_id") or "")
    proven = False
    for row in record.results_json or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "") != "independent_solver":
            continue
        if str(row.get("evidence_id") or "") != solver_id:
            continue
        if str(row.get("item_id") or "") != str(question.id):
            continue
        if str(row.get("derived_answer_key") or "") != evidence.answer_key:
            return False, "audit_solver_key_mismatch"
        proven = True
        break
    if not proven:
        return False, "independent_solver_not_proven"
    if meta.get("day9_veto") is True:
        return False, "day9_veto"
    return True, None