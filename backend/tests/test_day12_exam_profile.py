from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_advanced.constants import JEE_ADVANCED_PACK_CODE, PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import (
    describe_exam_profile,
    ensure_exam_version,
    ensure_jee_advanced_exam_pack,
)
from app.models.examination import ExamPack, ExamSection


def test_d12_06_07_two_paper_pcm_hierarchy() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        pack = ensure_jee_advanced_exam_pack(session)
        version = ensure_exam_version(
            session,
            pack=pack,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            academic_year="2026",
        )
        session.commit()

        persisted_pack = session.scalar(
            select(ExamPack).where(ExamPack.code == JEE_ADVANCED_PACK_CODE)
        )
        assert persisted_pack is not None
        assert persisted_pack.code == JEE_ADVANCED_PACK_CODE

        papers = session.scalars(
            select(ExamSection).where(
                ExamSection.exam_version_id == version.id,
                ExamSection.parent_section_id.is_(None),
            )
        ).all()
        assert {p.code for p in papers} == {PAPER_1_CODE, PAPER_2_CODE}
        profile = describe_exam_profile(version)
        assert profile["paper_count"] == 2
        assert profile["duration_minutes_per_paper"] == 180
