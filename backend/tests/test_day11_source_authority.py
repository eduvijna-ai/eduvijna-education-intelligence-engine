from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.constants import (
    JEE_MAIN_EXAM_PACK_CODE,
    JEE_MAIN_VERSION_2027,
    NTA_2027_BULLETIN_SOURCE_CODE,
    NTA_2027_SYLLABUS_SOURCE_CODE,
)
from app.jee_main_exam_intelligence.enums import OfficialPatternAuthorityStatus
from app.jee_main_exam_intelligence.exam_catalogue import (
    ensure_jee_main_exam_catalogue,
    get_exam_version,
)
from app.jee_main_exam_intelligence.source_authority import (
    evaluate_official_pattern_authority,
    register_nta_2027_candidate_sources,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_nta_candidates_stage_without_verification() -> None:
    with _session() as session:
        ids = register_nta_2027_candidate_sources(session)
        session.commit()
        assert NTA_2027_BULLETIN_SOURCE_CODE in ids
        assert NTA_2027_SYLLABUS_SOURCE_CODE in ids
        ensure_jee_main_exam_catalogue(session)
        version = get_exam_version(
            session, pack_code=JEE_MAIN_EXAM_PACK_CODE, version_code=JEE_MAIN_VERSION_2027
        )
        status, refs, _ = evaluate_official_pattern_authority(
            session,
            exam_version=version,
            exam_version_code=JEE_MAIN_VERSION_2027,
        )
        assert status == OfficialPatternAuthorityStatus.OFFICIAL_PATTERN_NOT_VERIFIED
        assert all(not r.verified_for_official_pattern for r in refs)
