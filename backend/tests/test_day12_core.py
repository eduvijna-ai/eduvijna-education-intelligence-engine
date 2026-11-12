from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.constants import (
    EDUVIJNA_DERIVED_TOPIC_GROUP,
    JEE_ADVANCED_PACK_CODE,
    MATHEMATICS_SUBJECT,
    PAPER_1_CODE,
    PAPER_2_CODE,
)
from app.jee_advanced.contracts import SubjectPracticeRequest, TopicPracticeRequest
from app.jee_advanced.core_test_fixtures import (
    seed_all_core_source_slots,
    seed_minimal_brochure_only,
    seed_persisted_math_questions,
)
from app.jee_advanced.enums import (
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.paper_pair_persistence import (
    PaperPairOutcome,
    PaperPairPersistRequest,
    persist_two_paper_pair,
)
from app.jee_advanced.practice_service import JeeAdvancedPracticeService
from app.jee_advanced.reference_allocator import (
    ReferenceAllocationRequest,
    allocate_reference_two_paper,
)
from app.jee_advanced.scoring import build_scoring_preview
from app.jee_advanced.source_authority import evaluate_reference_authority
from app.jee_advanced.source_registry import reference_evidence_ready
from app.models import ExamBlueprintRule
from app.models.enums import BlueprintRuleType
from app.models.question import TestDefinition as TestDefinitionRow
from app.source_intelligence.storage import LocalSourceStorage


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'core.db'}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.info["jee_core_storage"] = LocalSourceStorage(tmp_path / "private-sources")
    try:
        yield session
    finally:
        session.close()


def test_core01_runtime_id_forge_fails_without_session() -> None:
    assert reference_evidence_ready() is False
    assert reference_evidence_ready(None) is False


def test_core01_partial_slot_never_ready(db_session: Session) -> None:
    seed_minimal_brochure_only(db_session)
    report = evaluate_reference_authority(db_session)
    assert report.ready is False
    assert not reference_evidence_ready(db_session)


def test_core01_all_slots_test_fixture_can_be_trusted(db_session: Session) -> None:
    seed_all_core_source_slots(db_session)
    report = evaluate_reference_authority(db_session)
    assert report.ready is True
    assert reference_evidence_ready(db_session)


def test_core03_persisted_math_and_algebra_ten(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    db_session.commit()
    seed_persisted_math_questions(
        db_session,
        organization_id="org-core",
        institution_id="inst-core",
        exam_version_id=str(version.id),
    )
    svc = JeeAdvancedPracticeService(fixture_pool=None)
    math = svc.allocate_subject(
        SubjectPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            requested_count=10,
            organization_id="org-core",
            metadata_json={
                "use_persisted_pool": True,
                "institution_id": "inst-core",
            },
        ),
        session=db_session,
        exam_version_id=str(version.id),
    )
    assert math.verdict == AdvancedPlanVerdict.PASS
    assert math.delivered_count == 10
    assert all(q.metadata_json.get("persisted_selection") for q in math.questions)

    alg = svc.allocate_topic(
        TopicPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            topic_group=EDUVIJNA_DERIVED_TOPIC_GROUP,
            requested_count=10,
            organization_id="org-core",
            metadata_json={
                "use_persisted_pool": True,
                "institution_id": "inst-core",
            },
        ),
        session=db_session,
        exam_version_id=str(version.id),
    )
    assert alg.verdict == AdvancedPlanVerdict.PASS
    assert alg.delivered_count == 10


def test_core02_forged_scoring_ids_fail_closed(db_session: Session) -> None:
    preview = build_scoring_preview(
        {"rule_type": "multi_select", "full_marks": 4, "partial_marks": 2, "negative_marks": 1},
        session=db_session,
        approved_source_revision_id="00000000-0000-0000-0000-000000000001",
        blueprint_rule_id="00000000-0000-0000-0000-000000000002",
    )
    assert preview["source_pinned"] is False


def test_core04_reference_allocation_source_pending(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    db_session.commit()
    result = allocate_reference_two_paper(
        db_session,
        ReferenceAllocationRequest(
            organization_id="org-core",
            institution_id="inst-core",
            exam_version_id=str(version.id),
            paper_quotas={
                PAPER_1_CODE: {MATHEMATICS_SUBJECT: 2},
                PAPER_2_CODE: {MATHEMATICS_SUBJECT: 2},
            },
        ),
    )
    assert result.verdict == AdvancedPlanVerdict.SOURCE_PENDING


def test_core05_sqlite_pair_replay_cross_process(tmp_path: Path) -> None:
    db_path = tmp_path / "pair_replay.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
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
        qids = seed_persisted_math_questions(
            session,
            organization_id="org-core",
            institution_id="inst-core",
            exam_version_id=str(version.id),
            math_count=2,
            algebra_count=0,
        )
        req = PaperPairPersistRequest(
            idempotency_key="idem-1",
            organization_id="org-core",
            institution_id="inst-core",
            exam_version_id=str(version.id),
            pair_correlation_id="pair-abc",
            paper_definitions=(
                {
                    "paper_code": PAPER_1_CODE,
                    "title": "Paper 1",
                    "question_items": [{"question_id": qids[0], "section_code": "A"}],
                },
                {
                    "paper_code": PAPER_2_CODE,
                    "title": "Paper 2",
                    "question_items": [{"question_id": qids[1], "section_code": "B"}],
                },
            ),
            source_revision_snapshot={},
            blueprint_snapshot={},
        )
        first = persist_two_paper_pair(session, req)
        session.commit()
        assert first.outcome == PaperPairOutcome.CREATED
        version_id = str(version.id)

    script = f"""
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import app.models
from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.paper_pair_persistence import PaperPairPersistRequest, persist_two_paper_pair
from app.jee_advanced.constants import PAPER_1_CODE, PAPER_2_CODE

engine = create_database_engine("sqlite:///{db_path}")
with Session(engine) as session:
    req = PaperPairPersistRequest(
        idempotency_key="idem-1",
        organization_id="org-core",
        institution_id="inst-core",
        exam_version_id="{version_id}",
        pair_correlation_id="pair-abc",
        paper_definitions=(
            {{
                "paper_code": PAPER_1_CODE,
                "title": "Paper 1",
                "question_items": [{{"question_id": "{qids[0]}", "section_code": "A"}}],
            }},
            {{
                "paper_code": PAPER_2_CODE,
                "title": "Paper 2",
                "question_items": [{{"question_id": "{qids[1]}", "section_code": "B"}}],
            }},
        ),
        source_revision_snapshot={{}},
        blueprint_snapshot={{}},
    )
    second = persist_two_paper_pair(session, req)
    print(second.outcome)
    print(",".join(second.test_definition_ids))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == "replayed"
    replay_ids = lines[1].split(",")
    assert len(replay_ids) == 2

    with Session(engine) as session:
        count = session.scalars(select(TestDefinitionRow)).all()
        assert len(count) == 2


def test_core02_attested_preview_with_db_rule(db_session: Session) -> None:
    revision_ids = seed_all_core_source_slots(db_session)
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    revision_id = revision_ids[0]
    rule = ExamBlueprintRule(
        exam_version_id=str(version.id),
        rule_type=BlueprintRuleType.DIFFICULTY_DISTRIBUTION.value,
        min_count=1,
        max_count=5,
        selector_json={"source_pinned_revision_id": revision_id},
    )
    db_session.add(rule)
    db_session.commit()
    preview = build_scoring_preview(
        {
            "rule_type": "multi_select",
            "full_marks": 4,
            "partial_marks": 2,
            "negative_marks": 1,
            "correct_options": ["A"],
        },
        session=db_session,
        approved_source_revision_id=revision_id,
        blueprint_rule_id=str(rule.id),
        exam_version_id=str(version.id),
    )
    assert preview["source_pinned"] is True
    assert preview["demonstration_only"] is False


def test_core05_conflict_on_tenant_change(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    qids = seed_persisted_math_questions(
        db_session,
        organization_id="org-core",
        institution_id="inst-core",
        exam_version_id=str(version.id),
        math_count=1,
        algebra_count=1,
    )
    req = PaperPairPersistRequest(
        idempotency_key="idem-x",
        organization_id="org-core",
        institution_id="inst-core",
        exam_version_id=str(version.id),
        pair_correlation_id="pair-x",
        paper_definitions=(
            {
                "paper_code": PAPER_1_CODE,
                "question_items": [{"question_id": qids[0]}],
            },
            {
                "paper_code": PAPER_2_CODE,
                "question_items": [{"question_id": qids[1]}],
            },
        ),
        source_revision_snapshot={},
        blueprint_snapshot={},
    )
    persist_two_paper_pair(db_session, req)
    db_session.commit()
    conflict = persist_two_paper_pair(
        db_session,
        PaperPairPersistRequest(
            idempotency_key="idem-x",
            organization_id="org-other",
            institution_id="inst-core",
            exam_version_id=str(version.id),
            pair_correlation_id="pair-x",
            paper_definitions=req.paper_definitions,
            source_revision_snapshot={},
            blueprint_snapshot={},
        ),
    )
    assert conflict.outcome == PaperPairOutcome.CONFLICT
