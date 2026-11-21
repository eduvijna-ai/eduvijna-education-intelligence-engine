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
from app.jee_advanced.issuance_snapshot import question_issuance_snapshot
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
from app.jee_advanced.source_authority import (
    evaluate_reference_authority,
    evaluate_slot_storage_integrity,
)
from app.jee_advanced.source_registry import reference_evidence_ready
from app.models import ExamBlueprintRule, Question
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


def test_core01_synthetic_slots_never_official_ready(db_session: Session) -> None:
    seed_all_core_source_slots(db_session)
    report = evaluate_reference_authority(db_session)
    assert report.ready is False
    assert not reference_evidence_ready(db_session)
    assert any("synthetic_evidence_marker" in issue for issue in report.issues)


def test_core01_storage_integrity_isolated_from_official_ready(db_session: Session) -> None:
    revision_id = seed_minimal_brochure_only(db_session)
    storage = db_session.info["jee_core_storage"]
    assert storage is not None
    result = evaluate_slot_storage_integrity(
        db_session,
        "jee_advanced.2026.brochure",
        storage=storage,
    )
    assert result.trusted is True
    assert result.revision_id == revision_id
    assert not reference_evidence_ready(db_session)


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
                "allow_labeled_test_fixtures": True,
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
                "allow_labeled_test_fixtures": True,
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
            synthetic_labeled_test_mode=True,
        )
        q0 = session.get(Question, qids[0])
        q1 = session.get(Question, qids[1])
        assert q0 is not None and q1 is not None
        issuance_record = {
            "issuance_record_version": "d12-f49-v1",
            "ordered_question_ids": [qids[0], qids[1]],
            "question_snapshots": {
                qids[0]: question_issuance_snapshot(
                    q0, organization_id="org-core", institution_id="inst-core"
                ),
                qids[1]: question_issuance_snapshot(
                    q1, organization_id="org-core", institution_id="inst-core"
                ),
            },
            "chain_evidence": {},
            "source_revision_snapshot": {},
            "blueprint_snapshot": {},
        }
        first = persist_two_paper_pair(session, req, issuance_record=issuance_record)
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
        synthetic_labeled_test_mode=True,
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


def test_core02_attested_preview_rejects_untrusted_revision(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    rule = ExamBlueprintRule(
        exam_version_id=str(version.id),
        rule_type=BlueprintRuleType.DIFFICULTY_DISTRIBUTION.value,
        min_count=1,
        max_count=5,
        selector_json={"source_pinned_revision_id": "00000000-0000-0000-0000-000000000099"},
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
        approved_source_revision_id="00000000-0000-0000-0000-000000000099",
        blueprint_rule_id=str(rule.id),
        exam_version_id=str(version.id),
    )
    assert preview["source_pinned"] is False
    assert preview["demonstration_only"] is True
    assert "revision_not_trusted" in preview["attestation_issues"]


def test_core02_attested_preview_rejects_non_marking_rule(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    rule = ExamBlueprintRule(
        exam_version_id=str(version.id),
        rule_type=BlueprintRuleType.DIFFICULTY_DISTRIBUTION.value,
        min_count=1,
        max_count=5,
        selector_json={"source_pinned_revision_id": "00000000-0000-0000-0000-000000000099"},
    )
    db_session.add(rule)
    db_session.commit()
    preview = build_scoring_preview(
        {"rule_type": "multi_select", "full_marks": 4, "partial_marks": 2, "negative_marks": 1},
        session=db_session,
        approved_source_revision_id="00000000-0000-0000-0000-000000000098",
        blueprint_rule_id=str(rule.id),
        exam_version_id=str(version.id),
    )
    assert preview["source_pinned"] is False
    assert preview["attestation_issues"]


def test_core03_reference_mode_cannot_use_labeled_test_pool(db_session: Session) -> None:
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
        math_count=10,
        algebra_count=0,
    )
    svc = JeeAdvancedPracticeService(fixture_pool=None)
    ref = svc.allocate_subject(
        SubjectPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.REFERENCE_2026,
            trust_mode=JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026,
            subject_code=MATHEMATICS_SUBJECT,
            requested_count=10,
            organization_id="org-core",
            metadata_json={
                "use_persisted_pool": True,
                "allow_labeled_test_fixtures": True,
                "institution_id": "inst-core",
            },
        ),
        session=db_session,
        exam_version_id=str(version.id),
    )
    assert ref.verdict in {
        AdvancedPlanVerdict.SOURCE_PENDING,
        AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED,
    }
    assert ref.delivered_count == 0


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
        synthetic_labeled_test_mode=True,
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
            synthetic_labeled_test_mode=True,
        ),
    )
    assert conflict.outcome == PaperPairOutcome.CONFLICT


def test_core03_chiefcurator_name_does_not_bypass_authority(db_session: Session) -> None:
    seed_all_core_source_slots(db_session, actor_id="chiefcurator")
    report = evaluate_reference_authority(db_session)
    assert report.ready is False
    assert any("authorized_curator_not_verified" in issue for issue in report.issues)


def test_core03_stale_validation_after_stem_change(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    db_session.commit()
    qids = seed_persisted_math_questions(
        db_session,
        organization_id="org-core",
        institution_id="inst-core",
        exam_version_id=str(version.id),
        math_count=1,
        algebra_count=0,
    )
    question = db_session.get(Question, qids[0])
    assert question is not None
    question.stem_text = question.stem_text + " tampered"
    db_session.commit()
    svc = JeeAdvancedPracticeService(fixture_pool=None)
    math = svc.allocate_subject(
        SubjectPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            requested_count=1,
            organization_id="org-core",
            metadata_json={
                "use_persisted_pool": True,
                "allow_labeled_test_fixtures": True,
                "institution_id": "inst-core",
            },
        ),
        session=db_session,
        exam_version_id=str(version.id),
    )
    assert math.verdict != AdvancedPlanVerdict.PASS


def test_core02_incomplete_rule_fields_rejected(db_session: Session) -> None:
    pack = ensure_jee_advanced_exam_pack(db_session)
    version = ensure_exam_version(
        db_session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    rule = ExamBlueprintRule(
        exam_version_id=str(version.id),
        rule_type=BlueprintRuleType.SCORING.value,
        marks_per_question=None,
        negative_marks=1,
        selector_json={"source_pinned_revision_id": "00000000-0000-0000-0000-000000000099"},
        metadata_json={"paper_code": PAPER_1_CODE},
    )
    db_session.add(rule)
    db_session.commit()
    preview = build_scoring_preview(
        {"rule_type": "multi_select", "full_marks": 4, "partial_marks": 2, "negative_marks": 1},
        session=db_session,
        approved_source_revision_id="00000000-0000-0000-0000-000000000099",
        blueprint_rule_id=str(rule.id),
        exam_version_id=str(version.id),
    )
    assert preview["source_pinned"] is False
    issues = preview["attestation_issues"]
    assert "revision_not_trusted" in issues or "missing_persisted_full_marks" in issues


def test_core05_replay_rejects_tampered_marks(db_session: Session) -> None:
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
        math_count=2,
        algebra_count=0,
    )
    base = PaperPairPersistRequest(
        idempotency_key="idem-marks",
        organization_id="org-core",
        institution_id="inst-core",
        exam_version_id=str(version.id),
        pair_correlation_id="pair-marks",
        paper_definitions=(
            {
                "paper_code": PAPER_1_CODE,
                "question_items": [
                    {"question_id": qids[0], "section_code": "A", "marks": 3.0}
                ],
            },
            {
                "paper_code": PAPER_2_CODE,
                "question_items": [
                    {"question_id": qids[1], "section_code": "B", "marks": 3.0}
                ],
            },
        ),
        source_revision_snapshot={"synthetic": "true"},
        blueprint_snapshot={"demo": True},
        synthetic_labeled_test_mode=True,
    )
    persist_two_paper_pair(db_session, base)
    db_session.commit()
    tampered = PaperPairPersistRequest(
        idempotency_key=base.idempotency_key,
        organization_id=base.organization_id,
        institution_id=base.institution_id,
        exam_version_id=base.exam_version_id,
        pair_correlation_id=base.pair_correlation_id,
        paper_definitions=(
            {
                "paper_code": PAPER_1_CODE,
                "question_items": [
                    {"question_id": qids[0], "section_code": "A", "marks": 4.0}
                ],
            },
            base.paper_definitions[1],
        ),
        source_revision_snapshot=base.source_revision_snapshot,
        blueprint_snapshot=base.blueprint_snapshot,
        synthetic_labeled_test_mode=True,
    )
    conflict = persist_two_paper_pair(db_session, tampered)
    assert conflict.outcome == PaperPairOutcome.CONFLICT
    assert (
        "marks_mismatch" in conflict.issue_codes
        or "idempotency_payload_mismatch" in conflict.issue_codes
    )
