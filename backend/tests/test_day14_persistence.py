from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.ca_imat_eapcet.constants import CA_FOUNDATION_PACK_CODE
from app.ca_imat_eapcet.contracts import AllocateRequest
from app.ca_imat_eapcet.enums import Day14ProfileKind, Day14SourceTrustMode, PlanVerdict
from app.ca_imat_eapcet.exam_profile import ensure_synthetic_demo_versions
from app.ca_imat_eapcet.persistence_bridge import attempt_canonical_issuance
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models import Question
from app.models.question import TestDefinition as CanonicalTestDefinition


def test_f01_empty_issuance_fail_closed() -> None:
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


def test_f01_persisted_rows_only_when_validated() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ca_ver, _, _ = ensure_synthetic_demo_versions(session)
        svc = Day14PracticeService()
        alloc = svc.allocate(
            AllocateRequest(
                exam_pack_code=CA_FOUNDATION_PACK_CODE,
                profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
                trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                paper_or_section="paper3_quantitative_aptitude",
                requested_count=3,
            )
        )
        assert alloc.verdict == PlanVerdict.PASS
        env = attempt_canonical_issuance(
            session=session,
            questions=alloc.questions,
            organization_id="org",
            institution_id="inst",
            exam_version_id=str(ca_ver.id),
            source_version="synthetic_demo",
            idempotency_key="ca3",
        )
        assert env.committed is True
        assert env.verdict == PlanVerdict.PASS
        count = session.scalar(select(func.count()).select_from(Question))
        assert int(count or 0) == 3
        td = session.scalar(
            select(CanonicalTestDefinition).where(CanonicalTestDefinition.code == "ca3")
        )
        assert td is not None


def test_f01_replay_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ca_ver, _, _ = ensure_synthetic_demo_versions(session)
        svc = Day14PracticeService()
        alloc = svc.allocate(
            AllocateRequest(
                exam_pack_code=CA_FOUNDATION_PACK_CODE,
                profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
                trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
                paper_or_section="paper3_quantitative_aptitude",
                requested_count=2,
            )
        )
        key = "replay-key"
        first = attempt_canonical_issuance(
            session=session,
            questions=alloc.questions,
            organization_id="org",
            institution_id="inst",
            exam_version_id=str(ca_ver.id),
            source_version="synthetic_demo",
            idempotency_key=key,
        )
        second = attempt_canonical_issuance(
            session=session,
            questions=alloc.questions,
            organization_id="org",
            institution_id="inst",
            exam_version_id=str(ca_ver.id),
            source_version="synthetic_demo",
            idempotency_key=key,
        )
        assert first.committed and second.committed
        count = session.scalar(select(func.count()).select_from(Question))
        assert int(count or 0) == 2