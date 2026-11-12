from __future__ import annotations

import hashlib
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.anythingllm.factory import build_anythingllm_adapter
from app.adapters.anythingllm.protocol import AnythingLLMAdapter
from app.adapters.anythingllm.types import AdapterError
from app.common.trust_execution import TrustExecutionMode
from app.core.config import get_settings
from app.jee_main_exam_intelligence.blueprint_snapshot import VerifiedBlueprintSnapshot
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanSlot
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    JeeMainSubjectCode,
    PaperPlanIssueCode,
)
from app.jee_main_exam_intelligence.syllabus_mapping import resolve_topic_codes
from app.jee_main_exam_intelligence.trusted_validation import (
    SYNTHETIC_JEE_MAIN_TRUST_TOKEN,
    synthetic_trust_permitted,
)
from app.knowledge_intelligence.indexing import index_source_revision
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.models.education_intelligence import ValidationAuditRun
from app.models.enums import QuestionStatus, QuestionType
from app.models.orchestration import OrchestrationIdempotencyRecord
from app.models.question import Question, QuestionOption
from app.orchestration.canonical_mapping import draft_to_canonical
from app.orchestration.checkpoint import ManagedCheckpointer, build_managed_checkpointer
from app.orchestration.control_session import open_control_session
from app.orchestration.contracts import (
    DeterministicValidationSummary,
    DraftQuestionItem,
    OrchestrationRequest,
    OrchestrationResult,
    QuestionOptionDraft,
    ResolvedScope,
    SolverResult,
)
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.exceptions import OrchestrationConfigurationError
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import build_day8_test_service, build_orchestration_request
from app.orchestration.gateway.factory import build_generation_gateway
from app.orchestration.gateway.protocol import GenerationGateway
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.math_tools import deterministic_math_check
from app.orchestration.service import OrchestrationService
from app.root_cause_intelligence.day6_binding_verify import verify_production_day6_binding


class OrchestrationScopeError(RuntimeError):
    """Production orchestration scope is incomplete."""


_INJECT_KI_KEY = "eduvijna_pgc_test_inject_ki_adapter"
_INJECT_CHECKPOINT_KEY = "eduvijna_pgc_test_inject_checkpointer"
_TEST_ENVELOPE_SESSION_FLAG = "eduvijna_day11_test_trust_envelope_enabled"


def _production_mcq_distinct_and_valid(options: list[QuestionOptionDraft]) -> str | None:
    if len(options) < 4:
        return None
    texts = {o.text.strip().lower() for o in options}
    if len(texts) < 4:
        return None
    correct = [o for o in options if o.is_correct]
    if len(correct) != 1:
        return None
    return correct[0].option_key


def trust_envelope_from_orchestration_result(
    result: OrchestrationResult,
) -> dict[str, dict[str, Any]]:
    meta = result.metadata_json or {}
    by_det = {
        str(entry.get("item_id")): entry
        for entry in (meta.get("deterministic_validation") or [])
        if entry.get("item_id")
    }
    by_solver = {
        str(entry.get("item_id")): entry
        for entry in (meta.get("solver_results") or [])
        if entry.get("item_id")
    }
    envelope: dict[str, dict[str, Any]] = {}
    for item in result.items:
        envelope[item.item_id] = {
            "deterministic": by_det.get(item.item_id),
            "solver": by_solver.get(item.item_id),
            "trust_source": "orchestration_result",
            "orchestration_run_id": result.run_id,
        }
    return envelope


def _scope_for_draft_trust(request: PaperPlanRequest) -> ResolvedScope:
    meta = request.metadata_json or {}
    scope_raw = meta.get("orchestration_scope")
    scope_dict = scope_raw if isinstance(scope_raw, dict) else {}
    return ResolvedScope(
        curriculum_version_id=scope_dict.get("curriculum_version_id")
        or meta.get("curriculum_version_id"),
        organization_id=scope_dict.get("organization_id") or request.organization_id,
        institution_id=scope_dict.get("institution_id") or request.institution_id,
        grade_year_code=scope_dict.get("grade_year_code"),
        medium_code=scope_dict.get("medium_code"),
        subject_code=(
            request.subject_code.value if request.subject_code else scope_dict.get("subject_code")
        ),
    )


def _draft_canonical_input_hash(
    draft: DraftQuestionItem, request: PaperPlanRequest
) -> str:
    scope = _scope_for_draft_trust(request)
    marks_raw = (request.metadata_json or {}).get("marks")
    marks = float(marks_raw) if marks_raw is not None else draft.marks
    return draft_to_canonical(draft, scope, request_marks=marks).canonical_hash()


def _production_trust_envelope_allowed(
    session: Session,
    request: PaperPlanRequest,
    draft: DraftQuestionItem,
    trust: dict[str, Any] | None,
) -> bool:
    """Authenticate orchestration evidence against its persisted terminal run.

    The explicitly injected test envelope is available only in a trusted test
    session; request metadata alone can never enable the bypass.
    """
    if trust is None:
        return False
    meta = request.metadata_json or {}
    if (
        session.info.get(_TEST_ENVELOPE_SESSION_FLAG) is True
        and meta.get("deterministic_test_trust_harness") == SYNTHETIC_JEE_MAIN_TRUST_TOKEN
        and meta.get("allow_test_trust_envelope") is True
    ):
        return True
    run_id = trust.get("orchestration_run_id")
    if trust.get("trust_source") != "orchestration_result" or not isinstance(run_id, str):
        return False
    if not run_id:
        return False
    # Day8's file-backed SQLite control records live in a separate
    # *.orchestration.sqlite database; the domain Session cannot read them.
    # PostgreSQL uses a committed independent control transaction too.
    with open_control_session(session) as control:
        record = control.scalar(
            select(OrchestrationIdempotencyRecord).where(
                OrchestrationIdempotencyRecord.run_id == run_id,
                OrchestrationIdempotencyRecord.status == "completed",
            )
        )
        persisted_result = dict(record.result_json or {}) if record else None
    if not persisted_result:
        return False
    try:
        stored = OrchestrationResult.model_validate(persisted_result)
    except (ValidationError, TypeError, ValueError):
        return False
    if stored.run_id != run_id or stored.status != OrchestrationRunStatus.COMPLETED:
        return False
    saved_item = next((item for item in stored.items if item.item_id == draft.item_id), None)
    if saved_item is None or saved_item.model_dump(mode="json") != draft.model_dump(mode="json"):
        return False
    recorded_envelope = trust_envelope_from_orchestration_result(stored).get(draft.item_id)
    return recorded_envelope == trust


def _production_independent_trust_ok(
    session: Session,
    *,
    draft: DraftQuestionItem,
    request: PaperPlanRequest,
    qtype_value: str,
    answer_key: str | None,
    trust: dict[str, Any] | None,
    source_revision_ids: list[str],
) -> tuple[bool, PaperPlanIssueCode | None]:
    if trust is None or not _production_trust_envelope_allowed(session, request, draft, trust):
        return False, PaperPlanIssueCode.INVALID_ANSWER
    det_raw = trust.get("deterministic")
    solver_raw = trust.get("solver")
    if not isinstance(det_raw, dict) or not isinstance(solver_raw, dict):
        return False, PaperPlanIssueCode.INVALID_ANSWER
    det = DeterministicValidationSummary.model_validate(det_raw)
    solver = SolverResult.model_validate(solver_raw)
    if det.blocking or det.review_required or det.item_id != draft.item_id:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    if solver.item_id != draft.item_id:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    if not solver.agrees_with_author:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    if not det.day6_validation_run_id or not det.input_hash:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    canonical_hash = _draft_canonical_input_hash(draft, request)
    if det.input_hash != canonical_hash:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    if det.day6_content_fingerprint and det.day6_content_fingerprint != canonical_hash:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    ok, _ = verify_production_day6_binding(
        session,
        item_id=draft.item_id,
        validation_run_id=det.day6_validation_run_id,
        input_hash=det.input_hash,
        learning_outcome_ids=list(det.learning_outcome_ids),
        competency_codes=list(det.competency_codes),
        organization_id=request.organization_id,
        institution_id=request.institution_id,
        curriculum_version_id=(request.metadata_json or {}).get("curriculum_version_id"),
    )
    if not ok:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    if qtype_value == QuestionType.MULTIPLE_CHOICE.value:
        if not answer_key or solver.proposed_answer_key is None:
            return False, PaperPlanIssueCode.INVALID_ANSWER
        if str(solver.proposed_answer_key).upper() != str(answer_key).upper():
            return False, PaperPlanIssueCode.INVALID_ANSWER
        check_status, mismatch = deterministic_math_check(draft, solver)
        if mismatch or check_status not in {"ok"}:
            return False, PaperPlanIssueCode.INVALID_ANSWER
    else:
        return False, PaperPlanIssueCode.INVALID_ANSWER
    if draft.source_revision_ids:
        allowed = set(source_revision_ids)
        if allowed and not set(draft.source_revision_ids).issubset(allowed):
            return False, PaperPlanIssueCode.INVALID_ANSWER
    return True, None


def _map_question_type(draft_type: str) -> tuple[str, JeeMainQuestionTypeQuota | None]:
    normalized = (draft_type or "single_choice").strip().lower()
    if normalized in {"numerical", "integer", "numeric"}:
        return QuestionType.NUMERICAL.value, JeeMainQuestionTypeQuota.NUMERICAL
    return QuestionType.MULTIPLE_CHOICE.value, JeeMainQuestionTypeQuota.MCQ


def _mcq_answer_valid(
    options: list[QuestionOptionDraft], *, execution_mode: TrustExecutionMode
) -> str | None:
    if synthetic_trust_permitted(execution_mode):
        min_options = 2
        if len(options) < min_options:
            return None
        correct = [o for o in options if o.is_correct]
        if len(correct) != 1:
            return None
        return correct[0].option_key
    return _production_mcq_distinct_and_valid(options)


def _numerical_answer_valid(
    draft: DraftQuestionItem, *, execution_mode: TrustExecutionMode
) -> dict[str, Any] | None:
    if execution_mode == TrustExecutionMode.PRODUCTION:
        return None
    meta = draft.metadata_json or {}
    numeric = meta.get("numeric_answer") or meta.get("numeric_value")
    if numeric is None:
        return None
    return {"numeric_value": numeric}


def lookup_day6_binding_for_item(session: Session, item_id: str) -> dict[str, Any] | None:
    stmt = select(ValidationAuditRun).order_by(ValidationAuditRun.created_at.desc())
    for run in session.scalars(stmt):
        meta = run.metadata_json or {}
        for entry in meta.get("validated_items") or []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("item_id")) != item_id:
                continue
            return {
                "day6_validation_run_id": str(run.id),
                "day6_input_hash": str(entry.get("input_hash") or run.input_hash or ""),
                "learning_outcome_ids": list(entry.get("learning_outcome_ids") or []),
                "competency_codes": list(entry.get("competency_codes") or []),
            }
    return None


def _draft_answer_json(
    draft: DraftQuestionItem,
    qtype_value: str,
    *,
    execution_mode: TrustExecutionMode,
) -> dict[str, Any] | None:
    if qtype_value == QuestionType.NUMERICAL.value:
        return _numerical_answer_valid(draft, execution_mode=execution_mode)
    key = _mcq_answer_valid(list(draft.options), execution_mode=execution_mode)
    return {"correct_option": key} if key else None


def acquire_orchestration_service(
    session: Session,
    request: PaperPlanRequest,
    gateway: GenerationGateway,
) -> tuple[dict[str, str], OrchestrationService]:
    """Synthetic harness uses Day8 fixture builder; production uses configured factories."""
    meta = request.metadata_json or {}
    if synthetic_trust_permitted(request.execution_mode):
        return build_day8_test_service(session, gateway=gateway, memory_checkpointer=True)

    scope_raw = meta.get("orchestration_scope")
    if not isinstance(scope_raw, dict):
        raise OrchestrationScopeError("production orchestration_scope required")
    required = (
        "curriculum_version_id",
        "learning_outcome_id",
        "organization_id",
        "official_revision_id",
    )
    missing = [key for key in required if not scope_raw.get(key)]
    if missing:
        raise OrchestrationScopeError(f"orchestration_scope missing: {', '.join(missing)}")
    if request.organization_id != scope_raw.get("organization_id"):
        raise OrchestrationScopeError("organization scope mismatch")
    for field in ("grade_year_code", "medium_code"):
        if not scope_raw.get(field):
            raise OrchestrationScopeError(f"orchestration_scope missing: {field}")

    settings = get_settings()
    inject_ki = session.info.get(_INJECT_KI_KEY)
    if inject_ki is not None:
        ki_adapter: AnythingLLMAdapter = inject_ki
    else:
        try:
            ki_adapter = build_anythingllm_adapter(settings, force_fake=False)
        except AdapterError as exc:
            raise OrchestrationConfigurationError(str(exc)) from exc

    inject_checkpoint = session.info.get(_INJECT_CHECKPOINT_KEY)
    managed: ManagedCheckpointer | None
    if inject_checkpoint is not None:
        managed = inject_checkpoint
        memory_cp = False
    else:
        durable = bool(meta.get("orchestration_durable_checkpoint", True))
        managed = build_managed_checkpointer(settings, memory_only=not durable)
        memory_cp = not durable

    gen_gateway = gateway
    if gen_gateway is None:
        try:
            gen_gateway = build_generation_gateway(settings, force_fake=False)
        except OrchestrationConfigurationError:
            raise

    indexed: set[str] = session.info.setdefault("eduvijna_jee_production_ki_indexed", set())
    for rev_key in ("official_revision_id", "injection_revision_id"):
        rev_id = scope_raw.get(rev_key)
        if rev_id and str(rev_id) not in indexed:
            index_source_revision(
                session,
                ki_adapter,
                str(rev_id),
                retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
            )
            indexed.add(str(rev_id))

    service = build_orchestration_service(
        session,
        settings,
        gateway=gen_gateway,
        knowledge_adapter=ki_adapter,
        checkpointer=managed,
        memory_checkpointer=memory_cp,
        force_fake=None,
    )
    return dict(scope_raw), service


def _existing_generated_question_matches(
    existing: Question,
    draft: DraftQuestionItem,
    request: PaperPlanRequest,
    subject: str,
) -> bool:
    """Never silently reuse a global external code for another paper or tenant."""
    meta = existing.metadata_json or {}
    if existing.status != QuestionStatus.APPROVED.value:
        return False
    if any(
        (
            meta.get("organization_id") != request.organization_id,
            meta.get("institution_id") != request.institution_id,
            meta.get("exam_version_code") != request.exam_version_code,
            meta.get("jee_main_subject_code") != subject,
            existing.stem_text != draft.stem_text,
        )
    ):
        return False
    if request.execution_mode == TrustExecutionMode.PRODUCTION and meta.get("synthetic_fixture"):
        return False
    qtype, _ = _map_question_type(draft.question_type)
    if existing.question_type != qtype:
        return False
    expected_answer = _draft_answer_json(draft, qtype, execution_mode=request.execution_mode)
    if expected_answer is None or existing.answer_json != expected_answer:
        return False
    if qtype == QuestionType.MULTIPLE_CHOICE.value:
        stored = sorted((o.option_key, o.text, o.is_correct) for o in existing.options)
        incoming = sorted((o.option_key, o.text, o.is_correct) for o in draft.options)
        if stored != incoming:
            return False
    return True


def persist_draft_items_as_jee_questions(
    session: Session,
    *,
    items: list[DraftQuestionItem],
    request: PaperPlanRequest,
    source_revision_ids: list[str],
    orchestration_trust: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Question], list[PaperPlanIssueCode]]:
    """Persist orchestration output without inventing answers, options, or production approval."""
    created: list[Question] = []
    issues: list[PaperPlanIssueCode] = []
    subject = request.subject_code.value if request.subject_code else "mathematics"
    production = request.execution_mode == TrustExecutionMode.PRODUCTION
    for draft in items:
        external_code = draft.item_id
        existing = session.scalar(
            select(Question).where(Question.external_code == external_code)
        )
        if existing is not None:
            if _existing_generated_question_matches(existing, draft, request, subject):
                created.append(existing)
            else:
                issues.append(PaperPlanIssueCode.REPLAY_IDEMPOTENCY_CONFLICT)
            continue

        qtype_value, _ = _map_question_type(draft.question_type)
        answer = _draft_answer_json(
            draft, qtype_value, execution_mode=request.execution_mode
        )
        if answer is None:
            issues.append(PaperPlanIssueCode.INVALID_ANSWER)
            continue

        topic_codes = (
            [request.topic_code]
            if request.topic_code
            else list(draft.metadata_json.get("official_topic_codes") or [])
        )
        derived_groups = (
            [request.derived_topic_group]
            if request.derived_topic_group
            else list(draft.metadata_json.get("derived_topic_groups") or [])
        )
        if production and not topic_codes and not derived_groups:
            issues.append(PaperPlanIssueCode.UNKNOWN_TOPIC)
            continue

        if production:
            if qtype_value == QuestionType.MULTIPLE_CHOICE.value:
                answer_key = answer.get("correct_option")
            else:
                answer_key = None
            item_trust = (orchestration_trust or {}).get(draft.item_id)
            trusted, trust_issue = _production_independent_trust_ok(
                session,
                draft=draft,
                request=request,
                qtype_value=qtype_value,
                answer_key=str(answer_key) if answer_key else None,
                trust=item_trust,
                source_revision_ids=source_revision_ids,
            )
            if not trusted:
                issues.append(trust_issue or PaperPlanIssueCode.INVALID_ANSWER)
                continue
            day6_binding = {
                "day6_validation_run_id": str(
                    (item_trust or {}).get("deterministic", {}).get("day6_validation_run_id")
                ),
                "day6_input_hash": str(
                    (item_trust or {}).get("deterministic", {}).get("input_hash") or ""
                ),
                "learning_outcome_ids": list(
                    (item_trust or {}).get("deterministic", {}).get("learning_outcome_ids") or []
                ),
                "competency_codes": list(
                    (item_trust or {}).get("deterministic", {}).get("competency_codes") or []
                ),
            }
        else:
            day6_binding = {}

        meta = {
            **(draft.metadata_json or {}),
            "jee_main_subject_code": subject,
            "exam_version_code": request.exam_version_code,
            "organization_id": request.organization_id,
            "institution_id": request.institution_id,
            "official_topic_codes": topic_codes,
            "derived_topic_groups": derived_groups,
            "allowed_source_revision_ids": list(
                dict.fromkeys([*source_revision_ids, *draft.source_revision_ids])
            ),
            "cognitive_level": draft.declared_cognitive_level or "apply",
            "competency_codes": list(draft.competency_codes or []),
            "primary_competency_code": (
                draft.competency_codes[0] if draft.competency_codes else None
            ),
            "learning_outcome_ids": list(
                day6_binding.get("learning_outcome_ids") or draft.learning_outcome_ids
            ),
            "generation_run_id": draft.metadata_json.get("run_id"),
            "orchestration_origin": True,
        }
        if day6_binding:
            meta["day6_validation_run_id"] = day6_binding["day6_validation_run_id"]
            meta["day6_input_hash"] = day6_binding["day6_input_hash"]
            meta["day6_validated"] = True
        if synthetic_trust_permitted(request.execution_mode):
            meta["synthetic_fixture"] = True
            meta["jee_main_trust_harness_token"] = SYNTHETIC_JEE_MAIN_TRUST_TOKEN
            status = QuestionStatus.APPROVED.value
        elif production:
            status = QuestionStatus.APPROVED.value
        else:
            status = QuestionStatus.DRAFT.value

        question = Question(
            external_code=external_code,
            origin_type="orchestration_generated",
            question_type=qtype_value,
            stem_text=draft.stem_text,
            answer_json=answer,
            status=status,
            metadata_json=meta,
        )
        session.add(question)
        session.flush()
        if qtype_value == QuestionType.MULTIPLE_CHOICE.value:
            for option in draft.options:
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
    return created, issues


def build_jee_production_orchestration_request(
    request: PaperPlanRequest,
    scope: dict[str, str],
    *,
    shortage: int,
    idempotency_key: str,
    max_repairs: int = 2,
) -> OrchestrationRequest:
    meta = request.metadata_json or {}
    subject = request.subject_code or JeeMainSubjectCode.MATHEMATICS
    topic_codes, topic_issues = resolve_topic_codes(
        subject_code=subject,
        topic_code=request.topic_code,
        derived_topic_group=request.derived_topic_group,
    )
    if topic_issues:
        raise OrchestrationScopeError("unverified topic in production orchestration request")
    revision_ids = list(meta.get("allowed_source_revision_ids") or [])
    for key in ("official_revision_id", "injection_revision_id"):
        rev = scope.get(key)
        if rev and str(rev) not in revision_ids:
            revision_ids.append(str(rev))
    default_query = f"jee main {subject.value}"
    if topic_codes:
        default_query = f"{default_query} {' '.join(topic_codes)}"
    retrieval_query = str(meta.get("retrieval_query") or default_query).strip()
    return OrchestrationRequest(
        idempotency_key=idempotency_key,
        requested_count=min(shortage, 20),
        curriculum_version_id=scope["curriculum_version_id"],
        exam_version_id=scope.get("exam_version_id") or meta.get("exam_version_id"),
        grade_year_code=str(scope["grade_year_code"]),
        medium_code=str(scope["medium_code"]),
        subject_code=subject.value,
        topic_codes=topic_codes,
        retrieval_profile_version=str(
            scope.get("retrieval_profile_version") or DEFAULT_RETRIEVAL_PROFILE_VERSION
        ),
        retrieval_query=retrieval_query,
        organization_id=scope["organization_id"],
        institution_id=scope.get("institution_id") or request.institution_id,
        marks=float(meta.get("marks") or 4),
        max_repairs=max_repairs,
        metadata_json={
            "jee_plan_id": request.plan_id,
            "jee_execution_mode": request.execution_mode.value,
            "learning_outcome_ids": [scope["learning_outcome_id"]],
            "allowed_source_revision_ids": revision_ids,
            **(
                {"fixture_scenario": str(meta["test_injected_generation_scenario"])}
                if meta.get("test_injected_generation_scenario")
                else {}
            ),
        },
    )


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
    scope_meta = request.metadata_json or {}
    curriculum_id = day8_ctx.get("curriculum_version_id") or scope_meta.get("curriculum_version_id")
    return base.model_copy(
        update={
            "exam_version_id": day8_ctx.get("exam_version_id") or scope_meta.get("exam_version_id"),
            "curriculum_version_id": curriculum_id,
            "organization_id": day8_ctx.get("organization_id") or request.organization_id,
            "institution_id": day8_ctx.get("institution_id") or request.institution_id,
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


def _run_orchestration_batch(
    service: OrchestrationService,
    orch_request: OrchestrationRequest,
    *,
    request: PaperPlanRequest,
) -> OrchestrationResult:
    meta = request.metadata_json or {}
    resume: HumanResumeDecision | dict[str, Any] | None = None
    human_policy = str(meta.get("orchestration_human_resume") or "")
    for _ in range(3):
        result = service.run(orch_request, resume=resume)
        resume = None
        if result.status != OrchestrationRunStatus.REVIEW_REQUIRED:
            return result
        if synthetic_trust_permitted(request.execution_mode) and human_policy == "approve":
            resume = HumanResumeDecision(action="approve")
            continue
        return result
    return result


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

    try:
        ctx, service = acquire_orchestration_service(session, request, gateway)
    except (OrchestrationScopeError, OrchestrationConfigurationError):
        issues.append(PaperPlanIssueCode.LIVE_GENERATION_NOT_CONFIGURED)
        return slots, issues, {"gateway_invoked": False, "orchestration_scope_error": True}
    if day8_ctx:
        ctx = {**ctx, **{k: v for k, v in day8_ctx.items() if v}}

    all_items: list[DraftQuestionItem] = []
    source_revision_ids: list[str] = []
    repair_summary: dict[str, int] = {}
    last_run_id = ""
    last_status = OrchestrationRunStatus.FAILED
    gateway_calls_before = len(gateway.call_history()) if hasattr(gateway, "call_history") else 0
    orchestration_trust: dict[str, dict[str, Any]] = {}
    try:
        for batch_index in range(len(empty)):
            batch_idem = f"{idem}-slot-{batch_index:03d}"
            if synthetic_trust_permitted(request.execution_mode):
                orch_request = build_jee_orchestration_request(
                    request,
                    ctx,
                    shortage=1,
                    scenario=scenario,
                    idempotency_key=batch_idem[:128],
                    max_repairs=int(meta.get("max_repairs", 2)),
                )
            else:
                orch_request = build_jee_production_orchestration_request(
                    request,
                    ctx,
                    shortage=1,
                    idempotency_key=batch_idem[:128],
                    max_repairs=int(meta.get("max_repairs", 2)),
                )
            orch_result = _run_orchestration_batch(service, orch_request, request=request)
            last_run_id = orch_result.run_id
            last_status = orch_result.status
            for key, value in (orch_result.repair_summary or {}).items():
                repair_summary[key] = repair_summary.get(key, 0) + int(value)
            if orch_result.status != OrchestrationRunStatus.COMPLETED:
                issues.append(PaperPlanIssueCode.INSUFFICIENT_VALIDATED_POOL)
                break
            batch_trust = trust_envelope_from_orchestration_result(orch_result)
            orchestration_trust.update(batch_trust)
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
        "production_orchestration_factory": not synthetic_trust_permitted(request.execution_mode),
    }
    if hasattr(gateway, "call_history"):
        audit["gateway_calls"] = len(gateway.call_history()) - gateway_calls_before
    if len(all_items) < len(empty):
        return slots, issues, audit

    questions, persist_issues = persist_draft_items_as_jee_questions(
        session,
        items=all_items,
        request=request,
        source_revision_ids=source_revision_ids,
        orchestration_trust=orchestration_trust or None,
    )
    issues.extend(persist_issues)
    if len(questions) < len(empty):
        issues.append(PaperPlanIssueCode.INSUFFICIENT_VALIDATED_POOL)
        return slots, issues, audit

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
