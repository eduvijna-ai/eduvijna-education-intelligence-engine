from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.constants import CANDIDATE_PAPER1_TOTAL_QUESTIONS
from app.jee_main_exam_intelligence.enums import PaperPlanIssueCode, PaperPlanVerdict
from app.jee_main_exam_intelligence.fixtures import (
    build_official_replica_request,
    build_practice_math_ten_request,
    seed_day11_fixture_context,
    synthetic_activate_nta_sources_for_harness,
)
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService
from app.models.enums import QuestionStatus
from app.models.question import Question


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_production_replica_fails_with_synthetic_json_sources(tmp_path: Path) -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        synthetic_activate_nta_sources_for_harness(
            session, exam_version_id=ctx["exam_version_2027_id"], storage_root=tmp_path / "store"
        )
        session.commit()
        service = JeeMainExamIntelligenceService()
        req = build_official_replica_request(ctx).model_copy(
            update={"execution_mode": TrustExecutionMode.PRODUCTION}
        )
        result = service.plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
        assert PaperPlanIssueCode.OFFICIAL_SOURCE_NOT_VERIFIED in result.issue_codes


def test_production_practice_rejects_synthetic_metadata_only_pool() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={"execution_mode": TrustExecutionMode.PRODUCTION}
        )
        result = service.plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
        assert result.actual_count == 0


def test_synthetic_replica_passes_with_explicit_fixture_mode(tmp_path: Path) -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        synthetic_activate_nta_sources_for_harness(
            session, exam_version_id=ctx["exam_version_2027_id"], storage_root=tmp_path / "store"
        )
        session.commit()
        service = JeeMainExamIntelligenceService()
        result = service.plan_paper(session, build_official_replica_request(ctx), persist=False)
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == CANDIDATE_PAPER1_TOTAL_QUESTIONS
        assert result.official_pattern_label == "synthetic_fixture_demonstration"
        assert result.scoring_preview["mcq_slot_count"] == 60
        assert result.scoring_preview["numerical_slot_count"] == 15


def test_metadata_only_fake_day6_rejected_in_production() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        q = Question(
            external_code="fake-meta-only",
            origin_type="teacher",
            question_type="multiple_choice",
            stem_text="fake",
            answer_json={"correct_option": "A"},
            status=QuestionStatus.APPROVED.value,
            metadata_json={
                "jee_main_subject_code": "mathematics",
                "organization_id": ctx["organization_id"],
                "institution_id": ctx["institution_id"],
                "day6_validated": True,
            },
        )
        session.add(q)
        session.commit()
        service = JeeMainExamIntelligenceService()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={"execution_mode": TrustExecutionMode.PRODUCTION, "requested_count": 1}
        )
        result = service.plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
