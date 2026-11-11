from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanResult
from app.jee_main_exam_intelligence.enums import PaperPlanVerdict
from app.jee_main_exam_intelligence.exam_catalogue import get_exam_version
from app.jee_main_exam_intelligence.persistence import persist_paper_plan
from app.jee_main_exam_intelligence.planner import plan_paper
from app.orchestration.gateway.protocol import GenerationGateway


def assemble_paper_with_persistence(
    session: Session,
    request: PaperPlanRequest,
    *,
    gateway: GenerationGateway | None = None,
    persist: bool = True,
) -> PaperPlanResult:
    """Deterministic assembly from validated pools; LLM generation stays on the Day8 gateway."""
    if request.metadata_json.get("require_live_generation") and gateway is None:
        return plan_paper(session, request).model_copy(
            update={"verdict": PaperPlanVerdict.FAIL}
        )
    if (
        request.execution_mode == TrustExecutionMode.PRODUCTION
        and request.metadata_json.get("require_live_generation")
        and gateway is not None
    ):
        del gateway  # gateway-bound generation orchestration reuses Day8 entrypoints (D11-27)
    result = plan_paper(session, request)
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
