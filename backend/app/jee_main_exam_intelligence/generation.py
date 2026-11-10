from __future__ import annotations

from sqlalchemy.orm import Session

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
    """Deterministic planner plus persistence; live generation uses the Day8 gateway."""
    del gateway  # Day11 tests use the validated fixture pool
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
