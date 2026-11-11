from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.allocator import (
    allocate_full_replica_slots,
    allocate_practice_slots,
)
from app.jee_main_exam_intelligence.blueprint_snapshot import load_production_blueprint_snapshot
from app.jee_main_exam_intelligence.constants import (
    CANDIDATE_MARKS_CORRECT,
    CANDIDATE_MARKS_INCORRECT,
    CANDIDATE_PAPER1_TOTAL_MARKS,
    CANDIDATE_PAPER1_TOTAL_QUESTIONS,
    JEE_MAIN_EXAM_PACK_CODE,
)
from app.jee_main_exam_intelligence.contracts import (
    OfficialSourceRegistrationRef,
    PaperPlanRequest,
    PaperPlanResult,
    PaperPlanSlot,
)
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    JeeMainSubjectCode,
    OfficialPatternAuthorityStatus,
    PaperPlanIssueCode,
    PaperPlanMode,
    PaperPlanVerdict,
)
from app.jee_main_exam_intelligence.exam_catalogue import get_exam_version
from app.jee_main_exam_intelligence.persistence import build_result_checksum
from app.jee_main_exam_intelligence.question_pool import (
    assign_questions_to_slots,
    load_validated_questions,
)
from app.jee_main_exam_intelligence.scoring import build_scoring_preview
from app.jee_main_exam_intelligence.source_authority import evaluate_official_pattern_authority
from app.jee_main_exam_intelligence.syllabus_mapping import (
    resolve_topic_codes,
    validate_subject_code,
)


def plan_paper(session: Session, request: PaperPlanRequest) -> PaperPlanResult:
    issues: list[PaperPlanIssueCode] = []
    exam_version = get_exam_version(
        session,
        pack_code=request.exam_pack_code or JEE_MAIN_EXAM_PACK_CODE,
        version_code=request.exam_version_code,
    )
    if exam_version is None:
        issues.append(PaperPlanIssueCode.STALE_EXAM_VERSION)
        return _result(
            request,
            PaperPlanVerdict.FAIL,
            [],
            issues,
            OfficialPatternAuthorityStatus.NOT_VERIFIED,
            [],
            blueprint_rule_ids=[],
            scoring_kwargs={},
        )

    authority_status, source_refs, _ = evaluate_official_pattern_authority(
        session,
        exam_version=exam_version,
        exam_version_code=request.exam_version_code,
        execution_mode=request.execution_mode,
        required_source_revision_ids=request.allowed_source_revision_ids,
    )

    if request.mode == PaperPlanMode.OFFICIAL_PATTERN_REPLICA:
        return _plan_official_replica(
            session,
            request,
            exam_version.id,
            authority_status,
            source_refs,
            issues,
        )

    return _plan_practice(
        session,
        request,
        exam_version.id,
        authority_status,
        source_refs,
        issues,
    )


def _plan_official_replica(
    session: Session,
    request: PaperPlanRequest,
    exam_version_id: str,
    authority_status: OfficialPatternAuthorityStatus,
    source_refs: list[OfficialSourceRegistrationRef],
    issues: list[PaperPlanIssueCode],
) -> PaperPlanResult:
    production = request.execution_mode == TrustExecutionMode.PRODUCTION
    if production and authority_status != OfficialPatternAuthorityStatus.VERIFIED:
        issues.append(PaperPlanIssueCode.OFFICIAL_SOURCE_NOT_VERIFIED)
        return _result(
            request,
            PaperPlanVerdict.FAIL,
            [],
            issues,
            authority_status,
            source_refs,
            blueprint_rule_ids=[],
            scoring_kwargs={},
        )
    if (
        not production
        and authority_status != OfficialPatternAuthorityStatus.SYNTHETIC_FIXTURE_DEMONSTRATION
    ):
        issues.append(PaperPlanIssueCode.OFFICIAL_SOURCE_NOT_VERIFIED)
        return _result(
            request,
            PaperPlanVerdict.FAIL,
            [],
            issues,
            authority_status,
            source_refs,
            blueprint_rule_ids=[],
            scoring_kwargs={},
        )

    exam_version = get_exam_version(
        session,
        pack_code=request.exam_pack_code or JEE_MAIN_EXAM_PACK_CODE,
        version_code=request.exam_version_code,
    )
    assert exam_version is not None
    total_questions = CANDIDATE_PAPER1_TOTAL_QUESTIONS
    marks_correct = CANDIDATE_MARKS_CORRECT
    marks_incorrect = CANDIDATE_MARKS_INCORRECT
    expected_max = CANDIDATE_PAPER1_TOTAL_MARKS
    blueprint_rule_ids: list[str] = []
    if production:
        snapshot = load_production_blueprint_snapshot(session, exam_version)
        if snapshot is None:
            issues.append(PaperPlanIssueCode.UNAPPROVED_OFFICIAL_POLICY)
            return _result(
                request,
                PaperPlanVerdict.FAIL,
                [],
                issues,
                authority_status,
                source_refs,
                blueprint_rule_ids=[],
                scoring_kwargs={},
            )
        total_questions = snapshot.total_questions
        marks_correct = snapshot.marks_correct
        marks_incorrect = snapshot.marks_incorrect
        expected_max = snapshot.total_marks
        blueprint_rule_ids = list(snapshot.blueprint_rule_ids)

    slots, alloc_issues = allocate_full_replica_slots()
    issues.extend(alloc_issues)
    filled_slots: list[PaperPlanSlot] = []
    for subject in JeeMainSubjectCode:
        for qtype in (JeeMainQuestionTypeQuota.MCQ, JeeMainQuestionTypeQuota.NUMERICAL):
            subset = [
                s
                for s in slots
                if s.subject_code == subject and s.question_type == qtype
            ]
            questions, load_issues = load_validated_questions(
                session,
                subject=subject,
                topic_codes=[],
                derived_topic_group=None,
                organization_id=request.organization_id,
                institution_id=request.institution_id,
                exam_version_id=exam_version_id,
                allowed_source_revision_ids=request.allowed_source_revision_ids,
                question_type_quota=qtype,
                execution_mode=request.execution_mode,
            )
            issues.extend(load_issues)
            filled, assign_issues = assign_questions_to_slots(
                subset,
                questions,
                marks=marks_correct,
                negative_marks=marks_incorrect,
            )
            issues.extend(assign_issues)
            filled_slots.extend(filled)

    actual = len([s for s in filled_slots if s.question_id])
    verdict = (
        PaperPlanVerdict.PASS
        if actual == total_questions and not issues
        else PaperPlanVerdict.FAIL
    )
    if actual != total_questions:
        issues.append(PaperPlanIssueCode.COUNT_MISMATCH)
    return _result(
        request,
        verdict,
        filled_slots,
        issues,
        authority_status,
        source_refs,
        blueprint_rule_ids=blueprint_rule_ids,
        scoring_kwargs={
            "marks_correct": marks_correct,
            "marks_incorrect": marks_incorrect,
            "expected_maximum": expected_max,
        },
    )


def _plan_practice(
    session: Session,
    request: PaperPlanRequest,
    exam_version_id: str,
    authority_status: OfficialPatternAuthorityStatus,
    source_refs: list[OfficialSourceRegistrationRef],
    issues: list[PaperPlanIssueCode],
) -> PaperPlanResult:
    if request.requested_count is None or request.subject_code is None:
        issues.append(PaperPlanIssueCode.IMPOSSIBLE_QUOTA)
        return _result(
            request,
            PaperPlanVerdict.FAIL,
            [],
            issues,
            authority_status,
            source_refs,
            blueprint_rule_ids=[],
            scoring_kwargs={},
        )

    subject = validate_subject_code(request.subject_code.value)
    if subject is None:
        issues.append(PaperPlanIssueCode.UNKNOWN_SUBJECT)
        return _result(
            request,
            PaperPlanVerdict.FAIL,
            [],
            issues,
            authority_status,
            source_refs,
            blueprint_rule_ids=[],
            scoring_kwargs={},
        )

    topic_codes, topic_issues = resolve_topic_codes(
        subject_code=subject,
        topic_code=request.topic_code,
        derived_topic_group=request.derived_topic_group,
    )
    issues.extend(topic_issues)
    if topic_issues:
        return _result(
            request,
            PaperPlanVerdict.FAIL,
            [],
            issues,
            authority_status,
            source_refs,
            blueprint_rule_ids=[],
            scoring_kwargs={},
        )

    slots, alloc_issues = allocate_practice_slots(
        subject=subject,
        count=request.requested_count,
        topic_code=request.topic_code,
        derived_topic_group=request.derived_topic_group,
    )
    issues.extend(alloc_issues)
    questions, load_issues = load_validated_questions(
        session,
        subject=subject,
        topic_codes=topic_codes,
        derived_topic_group=request.derived_topic_group,
        organization_id=request.organization_id,
        institution_id=request.institution_id,
        exam_version_id=exam_version_id,
        allowed_source_revision_ids=request.allowed_source_revision_ids,
        execution_mode=request.execution_mode,
    )
    issues.extend(load_issues)

    filled, assign_issues = assign_questions_to_slots(
        slots,
        questions,
        marks=CANDIDATE_MARKS_CORRECT,
        negative_marks=CANDIDATE_MARKS_INCORRECT,
    )
    issues.extend(assign_issues)
    actual = len([s for s in filled if s.question_id])
    unique_issues = list(dict.fromkeys(issues))
    if actual != request.requested_count:
        unique_issues.append(PaperPlanIssueCode.COUNT_MISMATCH)
        verdict = PaperPlanVerdict.FAIL
    elif unique_issues:
        verdict = PaperPlanVerdict.FAIL
    else:
        verdict = PaperPlanVerdict.PASS
    return _result(
        request,
        verdict,
        filled,
        unique_issues,
        authority_status,
        source_refs,
        blueprint_rule_ids=[],
        scoring_kwargs={},
    )


def _result(
    request: PaperPlanRequest,
    verdict: PaperPlanVerdict,
    slots: list[PaperPlanSlot],
    issues: list[PaperPlanIssueCode],
    authority_status: OfficialPatternAuthorityStatus,
    source_refs: list[OfficialSourceRegistrationRef],
    *,
    blueprint_rule_ids: list[str],
    scoring_kwargs: dict[str, float],
) -> PaperPlanResult:
    requested = (
        request.requested_count
        if request.mode == PaperPlanMode.PRACTICE_EXACT_COUNT
        else CANDIDATE_PAPER1_TOTAL_QUESTIONS
    )
    source_ids = [r.revision_id for r in source_refs if r.revision_id]
    checksum = build_result_checksum(
        request,
        slots,
        source_revision_refs=source_ids,
        blueprint_rule_ids=blueprint_rule_ids,
    )
    official_label = authority_status.value
    if authority_status == OfficialPatternAuthorityStatus.SYNTHETIC_FIXTURE_DEMONSTRATION:
        official_label = "synthetic_fixture_demonstration"
    return PaperPlanResult(
        plan_id=request.plan_id,
        verdict=verdict,
        mode=request.mode,
        exam_version_code=request.exam_version_code,
        requested_count=requested,
        actual_count=len([s for s in slots if s.question_id]),
        slots=slots,
        issue_codes=list(dict.fromkeys(issues)),
        plan_checksum=checksum,
        official_pattern_label=official_label,
        source_revision_refs=source_ids,
        scoring_preview=build_scoring_preview(slots, **scoring_kwargs),
        metadata_json={
            "authority_status": authority_status.value,
            "execution_mode": request.execution_mode.value,
        },
    )
