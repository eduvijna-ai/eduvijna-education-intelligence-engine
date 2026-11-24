from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.ca_imat_eapcet.constants import CA_FOUNDATION_PACK_CODE, EAPCET_PACK_CODE, IMAT_PACK_CODE
from app.ca_imat_eapcet.exam_profile import ensure_day14_exam_packs, ensure_synthetic_demo_versions
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models.examination import ExamPack


def test_exam_packs_bootstrap_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_day14_exam_packs(session)
        ensure_day14_exam_packs(session)
        codes = set(
            session.scalars(
                select(ExamPack.code).where(
                    ExamPack.code.in_([CA_FOUNDATION_PACK_CODE, IMAT_PACK_CODE, EAPCET_PACK_CODE])
                )
            ).all()
        )
        assert codes == {CA_FOUNDATION_PACK_CODE, IMAT_PACK_CODE, EAPCET_PACK_CODE}


def test_synthetic_versions_have_sections() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_synthetic_demo_versions(session)
        session.commit()
        ca, imat, eapcet = ensure_synthetic_demo_versions(session)
        assert ca.duration_minutes == 180
        assert imat.duration_minutes == 100
        assert eapcet.duration_minutes == 180