from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys


def test_exam_packs_bootstrap() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        cuet_ver, clat_ver = ensure_synthetic_demo_versions(session)
        session.commit()
        assert cuet_ver.exam_pack.code == CUET_PACK_CODE
        assert clat_ver.exam_pack.code == CLAT_PACK_CODE
        assert len(cuet_ver.sections) >= 1