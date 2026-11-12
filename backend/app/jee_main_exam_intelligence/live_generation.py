from __future__ import annotations

from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanResult
from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode, PaperPlanVerdict
from app.jee_main_exam_intelligence.gateway_resolve import resolve_live_generation_gateway
from app.jee_main_exam_intelligence.orchestration_bridge import fill_slots_via_orchestration
from app.jee_main_exam_intelligence.planner import plan_paper
from app.orchestration.exceptions import IdempotencyConflictError
from app.orchestration.gateway.protocol import GenerationGateway


def complete_live_generation_plan(
    session: Session,
    request: PaperPlanRequest,
    result: PaperPlanResult,
    gateway: GenerationGateway | None,
) -> PaperPlanResult:
    """D11-27–29: Day8 LangGraph fill for trusted pool shortages, then replan."""
    if not request.metadata_json.get("require_live_generation"):
        return result

    shortage = max(0, (result.requested_count or 0) - result.actual_count)
    if shortage <= 0 and result.slots:
        shortage = len([s for s in result.slots if not s.question_id])

    pool_complete = (
        result.verdict == PaperPlanVerdict.PASS
        and result.actual_count == result.requested_count
        and shortage <= 0
    )
    if pool_complete:
        return result.model_copy(
            update={
                "metadata_json": {
                    **(result.metadata_json or {}),
                    "generation_path": "validated_question_pool",
                    "gateway_invoked": False,
                }
            }
        )

    if shortage <= 0:
        return result

    gateway = resolve_live_generation_gateway(session, request, gateway)
    if gateway is None:
        return result.model_copy(
            update={
                "verdict": PaperPlanVerdict.FAIL,
                "issue_codes": list(
                    dict.fromkeys(
                        [
                            *result.issue_codes,
                            PaperPlanIssueCode.LIVE_GENERATION_NOT_CONFIGURED,
                        ]
                    )
                ),
            }
        )

    day8_ctx_raw = request.metadata_json.get("day8_fixture_context")
    day8_ctx = day8_ctx_raw if isinstance(day8_ctx_raw, dict) else None

    try:
        _slots, fill_issues, audit = fill_slots_via_orchestration(
            session,
            request=request,
            slots=result.slots,
            gateway=gateway,
            day8_ctx=day8_ctx,
        )
    except IdempotencyConflictError:
        return result.model_copy(
            update={
                "verdict": PaperPlanVerdict.FAIL,
                "issue_codes": list(
                    dict.fromkeys(
                        [
                            *result.issue_codes,
                            PaperPlanIssueCode.REPLAY_IDEMPOTENCY_CONFLICT,
                        ]
                    )
                ),
            }
        )

    session.flush()
    replanned = plan_paper(session, request)
    meta = {
        **(replanned.metadata_json or {}),
        **audit,
        "generation_path": "day8_orchestration",
        "shortage_before_fill": shortage,
    }
    issues = list(dict.fromkeys([*replanned.issue_codes, *fill_issues]))
    return replanned.model_copy(
        update={
            "metadata_json": meta,
            "issue_codes": issues,
        }
    )


def apply_live_generation_boundary(
    session: Session,
    request: PaperPlanRequest,
    result: PaperPlanResult,
    gateway: GenerationGateway | None,
) -> PaperPlanResult:
    return complete_live_generation_plan(session, request, result, gateway)
