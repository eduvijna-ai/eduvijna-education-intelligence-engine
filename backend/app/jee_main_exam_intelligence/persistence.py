from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.checksum import plan_checksum
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanResult
from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode, PaperPlanVerdict
from app.models.enums import TestStatus
from app.models.question import TestDefinition, TestQuestion


def persist_paper_plan(
    session: Session,
    *,
    request: PaperPlanRequest,
    result: PaperPlanResult,
    exam_version_id: str | None,
) -> tuple[PaperPlanResult, list[PaperPlanIssueCode]]:
    issues: list[PaperPlanIssueCode] = []
    if result.verdict != PaperPlanVerdict.PASS:
        return result, issues
    code = f"d11-{request.plan_id}"
    existing = session.scalar(select(TestDefinition).where(TestDefinition.code == code))
    checksum = result.plan_checksum
    if request.idempotency_key:
        stored_key = (existing.metadata_json or {}).get("idempotency_key") if existing else None
        stored_checksum = (existing.metadata_json or {}).get("plan_checksum") if existing else None
        if existing and stored_key == request.idempotency_key and stored_checksum == checksum:
            return result.model_copy(
                update={
                    "test_definition_id": existing.id,
                    "test_definition_code": existing.code,
                }
            ), issues
        if existing and stored_key == request.idempotency_key and stored_checksum != checksum:
            issues.append(PaperPlanIssueCode.REPLAY_IDEMPOTENCY_CONFLICT)
            return result.model_copy(
                update={
                    "verdict": PaperPlanVerdict.FAIL,
                    "issue_codes": result.issue_codes + issues,
                }
            ), issues

    if existing is None:
        definition = TestDefinition(
            code=code,
            title=f"Day11 paper {request.plan_id}",
            exam_version_id=exam_version_id,
            status=TestStatus.DRAFT.value,
            blueprint_json={
                "mode": request.mode.value,
                "requested_count": request.requested_count,
                "plan_checksum": checksum,
            },
            metadata_json={
                "idempotency_key": request.idempotency_key,
                "plan_checksum": checksum,
                "organization_id": request.organization_id,
            },
        )
        session.add(definition)
        session.flush()
    else:
        definition = existing
        session.execute(
            delete(TestQuestion).where(TestQuestion.test_definition_id == definition.id)
        )
        session.flush()

    for sequence, slot in enumerate(result.slots, start=1):
        if not slot.question_id:
            issues.append(PaperPlanIssueCode.COUNT_MISMATCH)
            continue
        session.add(
            TestQuestion(
                test_definition_id=definition.id,
                question_id=slot.question_id,
                sequence=sequence,
                section_code=slot.section_code.value if slot.section_code else None,
                marks=slot.marks,
                negative_marks=slot.negative_marks,
                metadata_json={
                    "subject_code": slot.subject_code.value,
                    "slot_id": slot.slot_id,
                },
            )
        )
    session.flush()
    return result.model_copy(
        update={
            "test_definition_id": definition.id,
            "test_definition_code": definition.code,
        }
    ), issues


def build_result_checksum(request: PaperPlanRequest, slot_ids: list[str]) -> str:
    return plan_checksum(
        {
            "plan_id": request.plan_id,
            "mode": request.mode.value,
            "exam_version_code": request.exam_version_code,
            "requested_count": request.requested_count,
            "subject": request.subject_code.value if request.subject_code else None,
            "derived_topic_group": request.derived_topic_group,
            "slot_ids": slot_ids,
        }
    )
