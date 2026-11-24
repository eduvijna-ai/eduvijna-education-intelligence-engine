from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.ca_imat_eapcet.constants import CA_FOUNDATION_PACK_CODE
from app.ca_imat_eapcet.contracts import AllocateRequest
from app.ca_imat_eapcet.enums import Day14ProfileKind, Day14SourceTrustMode, PlanVerdict
from app.ca_imat_eapcet.exam_profile import ensure_synthetic_demo_versions
from app.ca_imat_eapcet.persistence_bridge import attempt_canonical_issuance
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.synthetic_fixtures import build_ca_quant_pool
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models import Question
from app.models.question import TestDefinition as CanonicalTestDefinition


def test_s01_empty_issuance_contained() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ca_ver, _, _ = ensure_synthetic_demo_versions(session)
        env = attempt_canonical_issuance(
            session=session,
            questions=[],
            organization_id="org",
            institution_id="inst",
            exam_version_id=str(ca_ver.id),
            source_version="synthetic_demo",
            idempotency_key="empty",
        )
        assert env.verdict is PlanVerdict.NOT_READY
        assert env.committed is False
        assert env.persisted_question_ids == ()


def test_s01_no_persistence_side_effects_with_fixture_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ca_ver, _, _ = ensure_synthetic_demo_versions(session)
        session.add(
            Question(
                external_code="preexisting",
                origin_type="generated",
                question_type="single_choice",
                stem_text="unrelated",
                status="draft",
                exam_version_id=str(ca_ver.id),
            )
        )
        session.commit()
        count_before = int(session.scalar(select(func.count()).select_from(Question)) or 0)
        td_before = int(
            session.scalar(select(func.count()).select_from(CanonicalTestDefinition)) or 0
        )

        alloc = Day14PracticeService().allocate(
            AllocateRequest(
                exam_pack_code=CA_FOUNDATION_PACK_CODE,
                profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
                trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                paper_or_section="paper3_quantitative_aptitude",
                requested_count=3,
            )
        )
        env = attempt_canonical_issuance(
            session=session,
            questions=list(build_ca_quant_pool(size=3)),
            organization_id="org-other",
            institution_id="inst",
            exam_version_id=str(ca_ver.id),
            source_version="synthetic_demo",
            idempotency_key="replay-key",
        )
        assert env.committed is False
        assert env.verdict is PlanVerdict.NOT_READY
        count_after = int(session.scalar(select(func.count()).select_from(Question)) or 0)
        td_after = int(
            session.scalar(select(func.count()).select_from(CanonicalTestDefinition)) or 0
        )
        assert count_before == count_after == 1
        assert td_before == td_after == 0
        assert alloc.delivered_count == 0