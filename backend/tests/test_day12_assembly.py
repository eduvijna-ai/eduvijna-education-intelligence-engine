from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_advanced.constants import (
    JEE_ADVANCED_PACK_CODE,
    OFFICIAL_SUBJECTS,
    PAPER_1_CODE,
    PAPER_2_CODE,
)
from app.jee_advanced.contracts import AdvancedPaperPlanRequest
from app.jee_advanced.enums import (
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.planner import JeeAdvancedPaperPlanner
from app.jee_advanced.source_lifecycle import (
    register_discovery_sources,
    sync_slot_evidence_from_session,
)
from app.jee_advanced.source_registry import reference_evidence_ready
from app.jee_advanced.synthetic_paper_assembly import assemble_synthetic_paper_items


def test_requested_count_rejects_unknown_key() -> None:
    planner = JeeAdvancedPaperPlanner()
    result = planner.plan(
        AdvancedPaperPlanRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
            paper_codes=[PAPER_1_CODE, PAPER_2_CODE],
            requested_counts={"paper_9": 6},
        )
    )
    assert result.verdict == AdvancedPlanVerdict.FAIL


def test_pcm_assembly_delivers_six_per_paper_with_subjects() -> None:
    items, issues, audit = assemble_synthetic_paper_items(paper_codes=[PAPER_1_CODE, PAPER_2_CODE])
    assert not issues
    assert len(items[PAPER_1_CODE]) == 6
    subjects = {q.subject_code for q in items[PAPER_1_CODE]}
    assert subjects == set(OFFICIAL_SUBJECTS)
    assert audit[PAPER_1_CODE]["subjects"]["physics"] == 2


def test_source_lifecycle_registers_six_slots_source_pending() -> None:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ids = register_discovery_sources(session)
        assert len(ids) == 6
        sync_slot_evidence_from_session(session)
        assert reference_evidence_ready() is False
