"""F03-A: persisted, Day6-validated synthetic CUET Mathematics pool."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.cuet_clat.constants import CUET_PACK_CODE, CUET_QUESTIONS_PER_TEST, MATHEMATICS_DOMAIN
from app.cuet_clat.contracts import CuetPracticeRequest, CuetSingleTestRequest
from app.cuet_clat.cuet_persisted_pool import seed_validated_cuet_math_questions
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.cuet_clat.persisted_context import PersistedCuetSelectionContext
from app.cuet_clat.practice_service import CuetPracticeService
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models import Question


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _persisted_ctx(
    session: Session,
    *,
    org: str = "org-f03a",
    inst: str = "inst-f03a",
) -> PersistedCuetSelectionContext:
    cuet_ver, _ = ensure_synthetic_demo_versions(session)
    return PersistedCuetSelectionContext(
        exam_version_id=str(cuet_ver.id),
        organization_id=org,
        institution_id=inst,
        academic_year="2026",
    )


def _synthetic_request(count: int = 10) -> CuetPracticeRequest:
    return CuetPracticeRequest(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        requested_count=count,
        academic_year="2026",
        medium_code="english",
        organization_id="org-f03a",
    )


def test_f03a_seed_and_math10_persisted_positive() -> None:
    with _session() as session:
        ctx = _persisted_ctx(session)
        seeded = seed_validated_cuet_math_questions(
            session,
            organization_id=ctx.organization_id,
            institution_id=ctx.institution_id,
            exam_version_id=ctx.exam_version_id,
            pool_size=50,
        )
        assert len(seeded) == 50
        svc = CuetPracticeService()
        result = svc.allocate_practice(
            _synthetic_request(10),
            session=session,
            persisted=ctx,
        )
        assert result.verdict == PlanVerdict.PASS
        assert result.delivered_count == 10
        assert result.metadata_json.get("validated_persisted_synthetic") is True
        assert result.metadata_json.get("demonstration_only") is False
        keys = {q.correct_key for q in result.questions}
        assert len(keys) > 1
        assert all(q.independently_validated for q in result.questions)
        assert all(q.stem_text and q.options for q in result.questions)
        assert all(q.validation_audit_id and q.solver_evidence_id for q in result.questions)


def test_f03a_single_test_50_persisted() -> None:
    with _session() as session:
        ctx = _persisted_ctx(session)
        seed_validated_cuet_math_questions(
            session,
            organization_id=ctx.organization_id,
            institution_id=ctx.institution_id,
            exam_version_id=ctx.exam_version_id,
            pool_size=50,
        )
        svc = CuetPracticeService()
        result = svc.assemble_single_test(
            CuetSingleTestRequest(
                exam_pack_code=CUET_PACK_CODE,
                profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
                trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
                test_subject_code=MATHEMATICS_DOMAIN,
                academic_year="2026",
                medium_code="english",
            ),
            session=session,
            persisted=ctx,
        )
        assert result.verdict == PlanVerdict.PASS
        assert result.question_count == CUET_QUESTIONS_PER_TEST


def test_f03a_short_pool_9_of_10_shortage() -> None:
    with _session() as session:
        ctx = _persisted_ctx(session)
        seed_validated_cuet_math_questions(
            session,
            organization_id=ctx.organization_id,
            institution_id=ctx.institution_id,
            exam_version_id=ctx.exam_version_id,
            pool_size=9,
        )
        svc = CuetPracticeService()
        result = svc.allocate_practice(
            _synthetic_request(10),
            session=session,
            persisted=ctx,
        )
        assert result.verdict == PlanVerdict.SHORTAGE
        assert result.questions == []


def test_f03a_altered_stem_vetoes_selection() -> None:
    with _session() as session:
        ctx = _persisted_ctx(session)
        ids = seed_validated_cuet_math_questions(
            session,
            organization_id=ctx.organization_id,
            institution_id=ctx.institution_id,
            exam_version_id=ctx.exam_version_id,
            pool_size=10,
        )
        row = session.get(Question, ids[0])
        assert row is not None
        row.stem_text = row.stem_text.replace("+", " plus ")
        session.commit()
        svc = CuetPracticeService()
        result = svc.allocate_practice(
            _synthetic_request(10),
            session=session,
            persisted=ctx,
        )
        assert result.verdict == PlanVerdict.SHORTAGE
        assert result.questions == []


def test_f03a_wrong_org_fails_closed() -> None:
    with _session() as session:
        ctx = _persisted_ctx(session)
        seed_validated_cuet_math_questions(
            session,
            organization_id=ctx.organization_id,
            institution_id=ctx.institution_id,
            exam_version_id=ctx.exam_version_id,
            pool_size=15,
        )
        svc = CuetPracticeService()
        bad = _synthetic_request(10).model_copy(update={"organization_id": "foreign-org"})
        result = svc.allocate_practice(bad, session=session, persisted=ctx)
        assert result.verdict == PlanVerdict.FAIL
        assert IssueCode.TENANT_ISOLATION in result.issue_codes
        assert result.questions == []


def test_f03a_legacy_fixture_demo_unchanged() -> None:
    svc = CuetPracticeService()
    result = svc.allocate_practice(_synthetic_request(10))
    assert result.verdict == PlanVerdict.PASS
    assert result.metadata_json.get("demonstration_only") is True
    assert all(not q.independently_validated for q in result.questions)


def test_f03a_persisted_requires_session() -> None:
    with _session() as session:
        ctx = _persisted_ctx(session)
        svc = CuetPracticeService()
        result = svc.allocate_practice(_synthetic_request(10), session=None, persisted=ctx)
        assert result.verdict == PlanVerdict.NOT_READY
        assert IssueCode.MISSING_PERSISTED_CONTEXT in result.issue_codes