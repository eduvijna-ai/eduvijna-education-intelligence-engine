from __future__ import annotations

from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanResult
from app.jee_main_exam_intelligence.enums import PaperPlanVerdict
from app.jee_main_exam_intelligence.exam_catalogue import get_exam_version
from app.jee_main_exam_intelligence.gateway_resolve import (
    INJECT_GATEWAY_KEY,
    resolve_live_generation_gateway,
)
from app.jee_main_exam_intelligence.live_generation import apply_live_generation_boundary
from app.jee_main_exam_intelligence.persistence import persist_paper_plan
from app.jee_main_exam_intelligence.planner import plan_paper
from app.orchestration.gateway.protocol import GenerationGateway

# Re-export for tests and session injection.
__all__ = [
    "INJECT_GATEWAY_KEY",
    "assemble_paper_with_persistence",
    "resolve_live_generation_gateway",
]


def assemble_paper_with_persistence(
    session: Session,
    request: PaperPlanRequest,
    *,
    gateway: GenerationGateway | None = None,
    persist: bool = True,
) -> PaperPlanResult:
    """Deterministic assembly from validated pools; LLM generation stays on the Day8 gateway."""
    result = plan_paper(session, request)
    result = apply_live_generation_boundary(session, request, result, gateway)
    if result.verdict != PaperPlanVerdict.PASS:
        return result
    if not persist or result.verdict != PaperPlanVerdict.PASS:
        return result
    exam_version = get_exam_version(
        session,
        pack_code=request.exam_pack_code,
        version_code=request.exam_version_code,
    )
    persisted, issues = persist_paper_plan(
        session,
        request=request,
        result=result,
        exam_version_id=exam_version.id if exam_version else None,
    )
    if issues:
        return persisted.model_copy(
            update={
                "verdict": PaperPlanVerdict.FAIL,
                "issue_codes": list(dict.fromkeys([*persisted.issue_codes, *issues])),
            }
        )
    return persisted
