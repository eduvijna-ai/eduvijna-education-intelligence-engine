from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.constants import CANDIDATE_PAPER1_TOTAL_QUESTIONS
from app.jee_main_exam_intelligence.enums import PaperPlanVerdict
from app.jee_main_exam_intelligence.fixtures import (
    build_official_replica_request,
    build_practice_algebra_ten_request,
    build_practice_math_ten_request,
    seed_day11_fixture_context,
    synthetic_activate_nta_sources_for_harness,
)
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_practice_mathematics_exactly_ten() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        result = service.plan_paper(session, build_practice_math_ten_request(ctx))
        session.commit()
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 10
        assert result.requested_count == 10
        assert result.test_definition_id is not None


def test_practice_algebra_exactly_ten_no_filler() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        result = service.plan_paper(session, build_practice_algebra_ten_request(ctx))
        session.commit()
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == 10
        for slot in result.slots:
            assert slot.derived_topic_group == "algebra"


def test_official_replica_fail_closed_until_verified() -> None:
    from app.common.trust_execution import TrustExecutionMode

    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        result = service.plan_paper(
            session,
            build_official_replica_request(ctx).model_copy(
                update={"execution_mode": TrustExecutionMode.PRODUCTION}
            ),
            persist=False,
        )
        assert result.verdict == PaperPlanVerdict.FAIL
        assert result.actual_count == 0


def test_synthetic_harness_official_replica_seventy_five(tmp_path: Path) -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        synthetic_activate_nta_sources_for_harness(
            session, exam_version_id=ctx["exam_version_2027_id"], storage_root=tmp_path / "store"
        )
        session.commit()
        service = JeeMainExamIntelligenceService()
        result = service.plan_paper(session, build_official_replica_request(ctx))
        session.commit()
        assert result.verdict == PaperPlanVerdict.PASS
        assert result.actual_count == CANDIDATE_PAPER1_TOTAL_QUESTIONS
        assert result.official_pattern_label == "synthetic_fixture_demonstration"
        mcq = sum(1 for s in result.slots if s.question_type and s.question_type.value == "mcq")
        numerical = sum(
            1
            for s in result.slots
            if s.question_type and s.question_type.value == "numerical"
        )
        assert mcq == 60
        assert numerical == 15
