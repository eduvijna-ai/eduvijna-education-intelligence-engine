from __future__ import annotations

from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanResult
from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode, PaperPlanVerdict
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.exceptions import IdempotencyConflictError
from app.orchestration.gateway.protocol import GenerationGateway
from app.orchestration.idempotency import claim_idempotency


def apply_live_generation_boundary(
    session: Session,
    request: PaperPlanRequest,
    result: PaperPlanResult,
    gateway: GenerationGateway | None,
) -> PaperPlanResult:
    """D11-27–29: Day8 gateway boundary with idempotent claim before any model call."""
    if not request.metadata_json.get("require_live_generation"):
        return result

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

    if result.verdict == PaperPlanVerdict.PASS and result.actual_count == result.requested_count:
        return result.model_copy(
            update={
                "metadata_json": {
                    **(result.metadata_json or {}),
                    "generation_path": "validated_question_pool",
                    "gateway_invoked": False,
                }
            }
        )

    raw = request.metadata_json.get("orchestration_request")
    if not isinstance(raw, dict):
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
                "metadata_json": {
                    **(result.metadata_json or {}),
                    "remaining_live_generation_gate": True,
                },
            }
        )

    orch_request = OrchestrationRequest.model_validate(raw)
    try:
        terminal, run_id, status = claim_idempotency(session, orch_request)
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

    meta = {
        **(result.metadata_json or {}),
        "generation_path": "day8_orchestration_boundary",
        "orchestration_run_id": run_id,
        "orchestration_status": status,
        "gateway_invoked": status not in (None, "completed"),
        "remaining_live_generation_gate": result.verdict != PaperPlanVerdict.PASS,
    }
    if terminal is not None:
        meta["orchestration_terminal_status"] = terminal.status.value
    return result.model_copy(update={"metadata_json": meta})
