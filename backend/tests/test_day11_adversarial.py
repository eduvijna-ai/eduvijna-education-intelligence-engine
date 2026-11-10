from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
from app.jee_main_exam_intelligence.enums import (
    JeeMainSubjectCode,
    PaperPlanIssueCode,
    PaperPlanMode,
    PaperPlanVerdict,
)
from app.jee_main_exam_intelligence.fixtures import (
    build_practice_algebra_ten_request,
    build_practice_math_ten_request,
    seed_day11_fixture_context,
)
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_nine_of_ten_fails_count_invariant() -> None:
    from app.models.enums import QuestionStatus
    from app.models.question import Question

    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        algebra_questions = [
            q
            for q in session.scalars(select(Question))
            if (q.metadata_json or {}).get("derived_topic_groups") == ["algebra"]
        ]
        for question in algebra_questions[8:]:
            question.status = QuestionStatus.DRAFT.value
        session.commit()
        service = JeeMainExamIntelligenceService()
        req = build_practice_algebra_ten_request(ctx)
        result = service.plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
        assert result.actual_count < 10
        assert PaperPlanIssueCode.COUNT_MISMATCH in result.issue_codes


def test_foreign_tenant_blocks_pool() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        req = build_practice_math_ten_request(ctx).model_copy(
            update={"organization_id": "tenant-b"}
        )
        result = service.plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL


def test_unknown_subject_rejected() -> None:
    with _session() as session:
        ctx = seed_day11_fixture_context(session)
        session.commit()
        service = JeeMainExamIntelligenceService()
        req = PaperPlanRequest(
            plan_id="bad-subject",
            exam_version_code="2027",
            mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
            organization_id=ctx["organization_id"],
            subject_code=JeeMainSubjectCode.MATHEMATICS,
            topic_code="nope",
            requested_count=10,
        )
        req = req.model_copy(update={"subject_code": None})
        result = service.plan_paper(session, req, persist=False)
        assert result.verdict == PaperPlanVerdict.FAIL
