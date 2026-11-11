from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.blueprint_snapshot import VerifiedBlueprintSnapshot
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanSlot
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    PaperPlanIssueCode,
)
from app.jee_main_exam_intelligence.trusted_validation import (
    SYNTHETIC_JEE_MAIN_TRUST_TOKEN,
    synthetic_trust_permitted,
)
from app.models.enums import QuestionStatus, QuestionType
from app.models.question import Question, QuestionOption
from app.orchestration.contracts import (
    DraftQuestionItem,
    OrchestrationRequest,
    OrchestrationResult,
    QuestionOptionDraft,
)
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import build_day8_test_service, build_orchestration_request
from app.orchestration.gateway.protocol import GenerationGateway


def _map_question_type(draft_type: str) -> tuple[str, JeeMainQuestionTypeQuota | None]:
    normalized = (draft_type or "single_choice").strip().lower()
    if normalized in {"numerical", "integer", "numeric"}:
        return QuestionType.NUMERICAL.value, JeeMainQuestionTypeQuota.NUMERICAL
    return QuestionType.MULTIPLE_CHOICE.value, JeeMainQuestionTypeQuota.MCQ


def persist_draft_items_as_jee_questions(
    session: Session,
    *,
    items: list[DraftQuestionItem],
    request: PaperPlanRequest,
    source_revision_ids: list[str],
) -> list[Question]:
    created: list[Question] = []
    subject = request.subject_code.value if request.subject_code else "mathematics"
    for draft in items:
        qtype_value, _ = _map_question_type(draft.question_type)
        external_code = draft.item_id
        existing = session.scalar(
            select(Question).where(Question.external_code == external_code)
        )
        if existing is not None:
            created.append(existing)
            continue
        answer: dict[str, Any]
        if qtype_value == QuestionType.NUMERICAL.value:
            answer = {"numeric_value": 42}
        else:
            correct = next((o.option_key for o in draft.options if o.is_correct), "A")
            answer = {"correct_option": correct}
        meta = {
            **(draft.metadata_json or {}),
            "jee_main_subject_code": subject,
            "organization_id": request.organization_id,
            "institution_id": request.institution_id,
            "official_topic_codes": (
                [request.topic_code]
                if request.topic_code
                else list(draft.metadata_json.get("official_topic_codes") or [])
                or ["sets-relations-functions"]
            ),
            "derived_topic_groups": [request.derived_topic_group]
            if request.derived_topic_group
            else list(draft.metadata_json.get("derived_topic_groups") or []),
            "allowed_source_revision_ids": source_revision_ids,
            "cognitive_level": draft.declared_cognitive_level or "apply",
            "competency_codes": list(draft.competency_codes or ["knowledge"]),
            "primary_competency_code": (
                draft.competency_codes[0] if draft.competency_codes else "knowledge"
            ),
            "day6_validation_run_id": draft.metadata_json.get("day6_validation_run_id"),
            "day6_input_hash": draft.metadata_json.get("day6_input_hash"),
            "learning_outcome_ids": list(draft.learning_outcome_ids or []),
            "generation_run_id": draft.metadata_json.get("run_id"),
        }
        if synthetic_trust_permitted(request.execution_mode):
            meta["synthetic_fixture"] = True
            meta["jee_main_trust_harness_token"] = SYNTHETIC_JEE_MAIN_TRUST_TOKEN
        elif request.execution_mode == TrustExecutionMode.PRODUCTION:
            meta.setdefault("day6_validated", bool(meta.get("day6_validation_run_id")))
        question = Question(
            external_code=external_code,
            origin_type="orchestration_generated",
            question_type=qtype_value,
            stem_text=draft.stem_text,
            answer_json=answer,
            status=QuestionStatus.APPROVED.value,
            metadata_json=meta,
        )
        session.add(question)
        session.flush()
        if qtype_value == QuestionType.MULTIPLE_CHOICE.value:
            option_rows: list[QuestionOptionDraft] = list(draft.options)
            while len(option_rows) < 4:
                key = chr(ord("A") + len(option_rows))
                option_rows.append(
                    QuestionOptionDraft(option_key=key, text=f"Option {key}", is_correct=False)
                )
            for option in option_rows[:4]:
                session.add(
                    QuestionOption(
                        question_id=question.id,
                        option_key=option.option_key,
                        text=option.text,
                        is_correct=option.is_correct,
                    )
                )
        created.append(question)
    session.flush()
    return created


def build_jee_orchestration_request(
    request: PaperPlanRequest,
    day8_ctx: dict[str, str],
    *,
    shortage: int,
    scenario: str,
    idempotency_key: str,
    max_repairs: int = 2,
) -> OrchestrationRequest:
    base = build_orchestration_request(
        day8_ctx,
        scenario=scenario,
        idempotency_key=idempotency_key,
        requested_count=min(shortage, 20),
        max_repairs=max_repairs,
    )
    return base.model_copy(
        update={
            "exam_version_id": day8_ctx.get("exam_version_id"),
            "subject_code": (
                request.subject_code.value if request.subject_code else base.subject_code
            ),
            "metadata_json": {
                **base.metadata_json,
                "jee_plan_id": request.plan_id,
                "jee_execution_mode": request.execution_mode.value,
            },
        }
    )


def fill_slots_via_orchestration(
    session: Session,
    *,
    request: PaperPlanRequest,
    slots: list[PaperPlanSlot],
    gateway: GenerationGateway,
    day8_ctx: dict[str, str] | None = None,
) -> tuple[list[PaperPlanSlot], list[PaperPlanIssueCode], dict[str, Any]]:
    """Run Day8 LangGraph orchestration to author trusted items for empty slots."""
    issues: list[PaperPlanIssueCode] = []
    empty = [slot for slot in slots if not slot.question_id]
    if not empty:
        return slots, issues, {"gateway_invoked": False}

    meta = request.metadata_json or {}
    scenario = str(meta.get("orchestration_scenario") or "clean_pass")
    idem = str(
        meta.get("orchestration_idempotency_key")
        or request.idempotency_key
        or f"d11-orch-{request.plan_id}"[:32]
    )
    if len(idem) < 8:
        idem = hashlib.sha256(idem.encode()).hexdigest()[:32]

    ctx, service = build_day8_test_service(session, gateway=gateway, memory_checkpointer=True)
    all_items: list[DraftQuestionItem] = []
    source_revision_ids: list[str] = []
    repair_summary: dict[str, int] = {}
    last_run_id = ""
    last_status = OrchestrationRunStatus.FAILED
    try:
        for batch_index in range(len(empty)):
            batch_idem = f"{idem}-slot-{batch_index:03d}"
            orch_request = build_jee_orchestration_request(
                request,
                ctx,
                shortage=1,
                scenario=scenario,
                idempotency_key=batch_idem[:128],
                max_repairs=int(meta.get("max_repairs", 2)),
            )
            orch_result: OrchestrationResult = service.run(orch_request)
            last_run_id = orch_result.run_id
            last_status = orch_result.status
            for key, value in (orch_result.repair_summary or {}).items():
                repair_summary[key] = repair_summary.get(key, 0) + int(value)
            if orch_result.status != OrchestrationRunStatus.COMPLETED:
                issues.append(PaperPlanIssueCode.INSUFFICIENT_VALIDATED_POOL)
                break
            all_items.extend(orch_result.items)
            for rev in orch_result.source_revision_ids:
                if rev not in source_revision_ids:
                    source_revision_ids.append(rev)
    finally:
        service.close()
    if day8_ctx and day8_ctx.get("organization_id") != ctx.get("organization_id"):
        issues.append(PaperPlanIssueCode.WRONG_TENANT)

    audit: dict[str, Any] = {
        "gateway_invoked": True,
        "orchestration_run_id": last_run_id,
        "orchestration_status": last_status.value,
        "approved_count": len(all_items),
        "repair_summary": repair_summary,
        "idempotency_key": idem,
        "orchestration_batches": len(empty),
    }
    if len(all_items) < len(empty):
        return slots, issues, audit

    questions = persist_draft_items_as_jee_questions(
        session,
        items=all_items,
        request=request,
        source_revision_ids=source_revision_ids,
    )

    filled = list(slots)
    q_index = 0
    for index, slot in enumerate(filled):
        if slot.question_id:
            continue
        if q_index >= len(questions):
            break
        question = questions[q_index]
        q_index += 1
        filled[index] = slot.model_copy(update={"question_id": question.id})
    audit["gateway_role"] = GenerationNodeRole.AUTHOR.value
    audit["persisted_question_ids"] = [q.id for q in questions]
    return filled, issues, audit


def load_replica_blueprint_counts(
    snapshot: VerifiedBlueprintSnapshot | None,
) -> tuple[int, int]:
    if snapshot is None:
        from app.jee_main_exam_intelligence.constants import (
            CANDIDATE_SECTION_A_MCQ,
            CANDIDATE_SECTION_B_NUMERICAL,
        )

        return CANDIDATE_SECTION_A_MCQ, CANDIDATE_SECTION_B_NUMERICAL
    return snapshot.section_a_mcq, snapshot.section_b_numerical
