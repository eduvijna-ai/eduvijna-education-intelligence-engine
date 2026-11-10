from __future__ import annotations

from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.contracts import PaperPlanRequest, PaperPlanResult
from app.jee_main_exam_intelligence.generation import assemble_paper_with_persistence
from app.jee_main_exam_intelligence.historical_evidence import build_historical_analytics_report
from app.jee_main_exam_intelligence.source_authority import (
    detect_source_drift,
    evaluate_official_pattern_authority,
    register_nta_2027_candidate_sources,
)


class JeeMainExamIntelligenceService:
    def register_nta_candidate_sources(self, session: Session) -> dict[str, str]:
        return register_nta_2027_candidate_sources(session)

    def evaluate_official_authority(
        self, session: Session, *, exam_version_code: str
    ) -> dict[str, object]:
        from app.jee_main_exam_intelligence.exam_catalogue import get_exam_version

        version = get_exam_version(session, pack_code="jee-main", version_code=exam_version_code)
        status, refs, detail = evaluate_official_pattern_authority(session, exam_version=version)
        return {
            "status": status.value,
            "sources": [r.model_dump() for r in refs],
            "detail": detail,
        }

    def plan_paper(
        self, session: Session, request: PaperPlanRequest, *, persist: bool = True
    ) -> PaperPlanResult:
        return assemble_paper_with_persistence(session, request, persist=persist)

    def historical_analytics(self) -> dict[str, object]:
        return build_historical_analytics_report()

    def source_drift_detected(
        self, session: Session, *, revision_id: str, expected_checksum: str
    ) -> bool:
        return detect_source_drift(
            session,
            revision_id=revision_id,
            expected_checksum=expected_checksum,
        )
