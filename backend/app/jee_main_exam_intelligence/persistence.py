from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.checksum import plan_checksum
from app.jee_main_exam_intelligence.contracts import (
    PaperPlanRequest,
    PaperPlanResult,
    PaperPlanSlot,
)
from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode, PaperPlanVerdict
from app.models.enums import TestStatus
from app.models.question import TestDefinition, TestQuestion


def persistence_definition_code(request: PaperPlanRequest) -> str:
    org = request.organization_id or "unscoped"
    inst = request.institution_id or "none"
    return f"d11-{org}-{inst}-{request.exam_version_code}-{request.plan_id}"


def build_result_checksum(
    request: PaperPlanRequest,
    slots: list[PaperPlanSlot],
    *,
    source_revision_refs: list[str],
    blueprint_rule_ids: list[str] | None = None,
) -> str:
    question_ids = sorted(s.question_id for s in slots if s.question_id)
    return plan_checksum(
        {
            "plan_id": request.plan_id,
            "mode": request.mode.value,
            "execution_mode": request.execution_mode.value,
            "exam_pack_code": request.exam_pack_code,
            "exam_version_code": request.exam_version_code,
            "requested_count": request.requested_count,
            "subject": request.subject_code.value if request.subject_code else None,
            "topic_code": request.topic_code,
            "derived_topic_group": request.derived_topic_group,
            "organization_id": request.organization_id,
            "institution_id": request.institution_id,
            "slot_ids": [s.slot_id for s in slots],
            "question_ids": question_ids,
            "source_revision_refs": sorted(source_revision_refs),
            "blueprint_rule_ids": sorted(blueprint_rule_ids or []),
        }
    )


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

    code = persistence_definition_code(request)
    existing = session.scalar(select(TestDefinition).where(TestDefinition.code == code))
    checksum = result.plan_checksum

    if existing is not None:
        existing_meta = existing.metadata_json or {}
        stored_org = existing_meta.get("organization_id")
        if request.organization_id and stored_org != request.organization_id:
            issues.append(PaperPlanIssueCode.FOREIGN_TENANT_CONTENT)
            return result.model_copy(
                update={
                    "verdict": PaperPlanVerdict.FAIL,
                    "issue_codes": result.issue_codes + issues,
                }
            ), issues
        if request.institution_id and existing_meta.get("institution_id") != request.institution_id:
            issues.append(PaperPlanIssueCode.FOREIGN_TENANT_CONTENT)
            return result.model_copy(
                update={
                    "verdict": PaperPlanVerdict.FAIL,
                    "issue_codes": result.issue_codes + issues,
                }
            ), issues
        if exam_version_id and existing.exam_version_id not in (None, exam_version_id):
            issues.append(PaperPlanIssueCode.STALE_EXAM_VERSION)
            return result.model_copy(
                update={
                    "verdict": PaperPlanVerdict.FAIL,
                    "issue_codes": result.issue_codes + issues,
                }
            ), issues

    if request.idempotency_key and existing is not None:
        stored_key = (existing.metadata_json or {}).get("idempotency_key")
        stored_checksum = (existing.metadata_json or {}).get("plan_checksum")
        if stored_key == request.idempotency_key and stored_checksum == checksum:
            return result.model_copy(
                update={
                    "test_definition_id": existing.id,
                    "test_definition_code": existing.code,
                }
            ), issues
        if stored_key == request.idempotency_key and stored_checksum != checksum:
            issues.append(PaperPlanIssueCode.REPLAY_IDEMPOTENCY_CONFLICT)
            return result.model_copy(
                update={
                    "verdict": PaperPlanVerdict.FAIL,
                    "issue_codes": list(dict.fromkeys([*result.issue_codes, *issues])),
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
                "execution_mode": request.execution_mode.value,
                "requested_count": request.requested_count,
                "plan_checksum": checksum,
            },
            metadata_json={
                "idempotency_key": request.idempotency_key,
                "plan_checksum": checksum,
                "organization_id": request.organization_id,
                "institution_id": request.institution_id,
                "exam_version_code": request.exam_version_code,
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
        definition.metadata_json = {
            **(definition.metadata_json or {}),
            "plan_checksum": checksum,
            "idempotency_key": request.idempotency_key,
        }

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
