"""Issue #47 PROD-47-01…04 production integration gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.jee_advanced.core_test_fixtures import (
    _persist_day6_validation_run,
    seed_persisted_arithmetic_mcq_pair,
    seed_persisted_math_questions,
)
from app.jee_advanced.enums import AdvancedProfileKind
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.historical_inventory import list_historical_sources_by_year
from app.jee_advanced.independent_verification import (
    VerificationOutcome,
    verify_stored_mcq_by_id,
    verify_stored_multiselect_by_id,
    verify_stored_numerical_by_id,
)
from app.jee_advanced.orchestration_chain import (
    run_injected_author_solver_review_chain,
)
from app.jee_advanced.paper_pair_persistence import (
    PaperPairOutcome,
)
from app.jee_advanced.persisted_question_loader import PersistedAnswerScope
from app.jee_advanced.production_orchestration import (
    REQUIRED_CHAIN_STAGES,
    run_labeled_synthetic_pair_integration,
)
from app.jee_advanced.scope_ledger import load_repo_scope_counts
from app.jee_advanced.syllabus_graph import syllabus_graph_issue_codes
from app.models import Question, QuestionOption, Source
from app.models.curriculum import CurriculumNode, LearningOutcome
from app.models.education_intelligence import ValidationAuditRun
from app.models.enums import CurriculumNodeType, QuestionStatus, QuestionType
from app.orchestration.gateway.fake import FakeGenerationGateway


def _session(tmp_path: Path) -> Session:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'prod.sqlite'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _scope(org: str, inst: str, version_id: str | None = None) -> PersistedAnswerScope:
    return PersistedAnswerScope(
        organization_id=org,
        institution_id=inst,
        exam_version_id=version_id,
        expected_family="mcq",
    )


def test_prod47_01_stored_answer_by_id_and_units(tmp_path: Path) -> None:
    session = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-p47", "inst-p47"
    vid = str(version.id)
    seed_persisted_math_questions(
        session,
        organization_id=org,
        institution_id=inst,
        exam_version_id=vid,
        math_count=1,
        algebra_count=0,
    )
    q = session.scalars(select(Question)).first()
    assert q is not None
    qid = str(q.id)

    fail_z = verify_stored_mcq_by_id(
        session, question_id=qid, scope=_scope(org, inst, vid), selected="Z"
    )
    assert fail_z.outcome == VerificationOutcome.FAIL

    pass_a = verify_stored_mcq_by_id(
        session, question_id=qid, scope=_scope(org, inst, vid), selected="A"
    )
    assert pass_a.outcome == VerificationOutcome.PASS

    q.status = QuestionStatus.REJECTED.value
    session.commit()
    rejected = verify_stored_mcq_by_id(
        session, question_id=qid, scope=_scope(org, inst, vid), selected="A"
    )
    assert rejected.outcome == VerificationOutcome.REVIEW_REQUIRED
    assert "question_not_approved" in rejected.issue_codes

    session.close()


def test_prod47_01_numerical_kg_vs_m_and_zero_tolerance(tmp_path: Path) -> None:
    session = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-num", "inst-num"
    vid = str(version.id)
    q = Question(
        external_code="p47-num",
        origin_type="generated",
        exam_version_id=vid,
        question_type=QuestionType.NUMERICAL.value,
        stem_text="distance",
        answer_json={"value": "2.0", "units": "m"},
        rubric_json={"tolerance": 0, "units_required": True, "expected_units": "m"},
        status=QuestionStatus.APPROVED.value,
        metadata_json={
            "d12_core_test_fixture": True,
            "demonstration_only": True,
            "organization_id": org,
            "institution_id": inst,
            "day6_validation_audit_id": "audit-p47-num",
            "day6_solver_evidence_id": "solver-p47-num",
        },
    )
    session.add(q)
    session.flush()
    _persist_day6_validation_run(
        session, run_id="audit-p47-num", question=q, organization_id=org, institution_id=inst
    )
    session.commit()
    scope = PersistedAnswerScope(
        organization_id=org, institution_id=inst, exam_version_id=vid, expected_family="numerical"
    )
    wrong = verify_stored_numerical_by_id(
        session, question_id=str(q.id), scope=scope, submitted="2.0 kg"
    )
    assert wrong.outcome == VerificationOutcome.FAIL
    assert "numerical_units_mismatch" in wrong.issue_codes

    exact = verify_stored_numerical_by_id(
        session, question_id=str(q.id), scope=scope, submitted="2.0 m"
    )
    assert exact.outcome == VerificationOutcome.PASS

    nan_fail = verify_stored_numerical_by_id(
        session, question_id=str(q.id), scope=scope, submitted="nan m"
    )
    assert nan_fail.outcome == VerificationOutcome.REVIEW_REQUIRED
    session.close()


def test_prod47_01_multiselect_domain_and_org_audit(tmp_path: Path) -> None:
    session = _session(tmp_path)
    pack = ensure_jee_advanced_exam_pack(session)
    version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    org, inst = "org-ms", "inst-ms"
    vid = str(version.id)
    q = Question(
        external_code="p47-ms",
        origin_type="generated",
        exam_version_id=vid,
        question_type=QuestionType.MULTIPLE_CHOICE.value,
        stem_text="pick two",
        status=QuestionStatus.APPROVED.value,
        metadata_json={
            "d12_core_test_fixture": True,
            "organization_id": org,
            "institution_id": inst,
            "day6_validation_audit_id": "audit-ms",
            "day6_solver_evidence_id": "solver-ms",
        },
    )
    for key, correct in (("A", True), ("B", True), ("C", False)):
        q.options.append(
            QuestionOption(option_key=key, text=key, is_correct=correct, sequence=1)
        )
    session.add(q)
    session.flush()
    _persist_day6_validation_run(
        session, run_id="audit-ms", question=q, organization_id=org, institution_id=inst
    )
    session.commit()
    scope = PersistedAnswerScope(organization_id=org, institution_id=inst, exam_version_id=vid)
    bad_opt = verify_stored_multiselect_by_id(
        session, question_id=str(q.id), scope=scope, selected=frozenset({"A", "Z"})
    )
    assert bad_opt.outcome == VerificationOutcome.FAIL

    record = session.scalar(
        select(ValidationAuditRun).where(ValidationAuditRun.run_id == "audit-ms")
    )
    assert record is not None
    record.metadata_json = {
        "validated_items": [
            {
                "item_id": str(q.id),
                "input_hash": record.input_hash,
            }
        ],
        "scope": {},
    }
    session.commit()
    forged = verify_stored_multiselect_by_id(
        session, question_id=str(q.id), scope=scope, selected=frozenset({"A", "B"})
    )
    assert forged.outcome == VerificationOutcome.REVIEW_REQUIRED
    assert "validation_record_org_missing" in forged.issue_codes
    session.close()


def test_prod47_02_unknown_concept_and_incomplete_pcm(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from app.curriculum_intelligence.framework_structure import FrameworkStructureService
    from app.models.curriculum import (
        Competency,
        CurriculumPack,
        CurriculumVersion,
        EducationFramework,
    )
    from app.models.framework_structure import LearningOutcomeCompetencyLink
    from app.models.source import Source, SourceRevision
    from app.schemas.framework_structure import FrameworkNodeSpec

    session = _session(tmp_path)
    source = Source(
        source_type="official_syllabus",
        title="Synthetic syllabus",
        board_or_exam="jee_advanced",
        metadata_json={"d12_core_test_fixture": True},
    )
    session.add(source)
    session.flush()
    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum="a" * 64,
        source_snapshot_checksum="b" * 64,
        ingestion_method="upload",
        content_type="text/plain",
        byte_size=12,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_text="synthetic",
        extracted_checksum="a" * 64,
        metadata_json={"synthetic": True, "page_locator": "p.1"},
    )
    session.add(revision)
    session.flush()
    fw = EducationFramework(
        code="fw-p47-int", name="FW", country="IN", version_code="2026-draft"
    )
    session.add(fw)
    session.flush()
    pack = CurriculumPack(
        framework_id=fw.id,
        code="pack-p47",
        name="Pack",
        country="IN",
        source_revision_id=revision.id,
    )
    session.add(pack)
    session.flush()
    version = CurriculumVersion(
        curriculum_pack_id=pack.id,
        version_code="2026",
        source_revision_id=revision.id,
        status="active",
    )
    competency = Competency(
        framework_id=fw.id, code="comp-p47", name="Comp", source_revision_id=revision.id
    )
    session.add_all([version, competency])
    session.flush()
    service = FrameworkStructureService(session)
    nodes = service.upsert_nodes(
        framework=fw,
        revision=revision,
        specs=[
            FrameworkNodeSpec(
                level="stage",
                code="sec",
                title="Sec",
                publication_status="final",
                review_status="reviewed",
                source_locator="p.1",
            ),
            FrameworkNodeSpec(
                level="curricular_area",
                code="math",
                title="Math",
                parent_code="sec",
                publication_status="final",
                review_status="reviewed",
                source_locator="p.2",
            ),
            FrameworkNodeSpec(
                level="goal",
                code="g1",
                title="Goal",
                parent_code="math",
                publication_status="final",
                review_status="reviewed",
                source_locator="p.3",
            ),
            FrameworkNodeSpec(
                level="competency",
                code="c1",
                title="Competency",
                parent_code="g1",
                competency_id=UUID(competency.id),
                publication_status="final",
                review_status="reviewed",
                source_locator="p.4",
            ),
        ],
    )
    comp_node_id = str(nodes["c1"].id)
    rev_id = str(revision.id)
    cv_id = str(version.id)
    outcomes: list[LearningOutcome] = []
    for subj in ("physics", "chemistry", "mathematics"):
        concept = CurriculumNode(
            curriculum_version_id=cv_id,
            node_type=CurriculumNodeType.CONCEPT.value,
            code=f"c-{subj}",
            title=subj,
            source_revision_id=rev_id,
            source_locator=f"p.concept.{subj}",
        )
        session.add(concept)
        session.flush()
        lo = LearningOutcome(
            curriculum_version_id=cv_id,
            code=f"lo-{subj}",
            text=f"Outcome {subj}",
            source_revision_id=rev_id,
            source_locator=f"p.lo.{subj}",
            active=True,
            metadata_json={
                "subject_code": subj,
                "concept_node_id": str(concept.id),
                "mapping_reviewed": True,
                "d12_core_test_fixture": True,
            },
        )
        lo.nodes.append(concept)
        session.add(lo)
        session.flush()
        session.add(
            LearningOutcomeCompetencyLink(
                curriculum_version_id=cv_id,
                learning_outcome_id=str(lo.id),
                framework_id=str(fw.id),
                competency_node_id=comp_node_id,
                competency_node_level="competency",
                relationship_type="direct",
                status="direct",
                inferred=False,
                publication_status="final",
                review_status="reviewed",
                source_revision_id=rev_id,
                source_locator=f"p.link.{subj}",
                evidence_text="synthetic reviewed",
            )
        )
        outcomes.append(lo)
    session.commit()
    issues = syllabus_graph_issue_codes(
        session, outcomes=outcomes, curriculum_version_id=cv_id
    )
    assert issues == ()
    single_math = [outcomes[2]]
    pcm_gap = syllabus_graph_issue_codes(session, outcomes=single_math, curriculum_version_id=cv_id)
    assert any("pcm_subject_missing" in code for code in pcm_gap)
    session.close()


def test_prod47_03_orchestration_affirmative_and_unknown_review() -> None:
    gw = FakeGenerationGateway()
    ok = run_injected_author_solver_review_chain(
        gw,
        item_id="it-1",
        run_id="run-1",
        organization_id="org-orch",
        scenario="clean_pass",
    )
    assert ok.verdict.outcome == VerificationOutcome.PASS
    for stage in REQUIRED_CHAIN_STAGES:
        assert stage in ok.stages_completed

    gw2 = FakeGenerationGateway()
    original = gw2._review_payload

    def wrapper(role, scenario, item_id, payload):  # type: ignore[no-untyped-def]
        if scenario == "review_unknown":
            return {
                "reviewer": role.value,
                "item_id": item_id,
                "status": "",
                "issue_codes": [],
                "repair_instructions": [],
            }
        return original(role, scenario, item_id, payload)

    gw2._review_payload = wrapper  # type: ignore[method-assign]
    unknown = run_injected_author_solver_review_chain(
        gw2,
        item_id="it-2",
        run_id="run-2",
        organization_id="org-orch",
        scenario="review_unknown",
    )
    assert unknown.verdict.outcome == VerificationOutcome.REVIEW_REQUIRED
    assert "reviewer_verdict_missing" in unknown.verdict.issue_codes


def test_prod47_03_integrated_pair_cross_process(tmp_path: Path) -> None:
    db_path = tmp_path / "int-pair.db"
    engine = create_database_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    gateway_calls_first = 0
    test_ids: tuple[str, str] = ("", "")
    version_id = ""
    with Session(engine) as session:
        pack = ensure_jee_advanced_exam_pack(session)
        version = ensure_exam_version(
            session,
            pack=pack,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            academic_year="2026",
        )
        version_id = str(version.id)
        qids = seed_persisted_arithmetic_mcq_pair(
            session,
            organization_id="org-int",
            institution_id="inst-int",
            exam_version_id=version_id,
        )
        test_ids = (qids[0], qids[1])
        gateway = FakeGenerationGateway()
        integrated = run_labeled_synthetic_pair_integration(
            session,
            gateway,
            organization_id="org-int",
            institution_id="inst-int",
            exam_version_id=version_id,
            question_ids=test_ids,
            idempotency_key="idem-p47",
            pair_correlation_id="pair-p47",
            scenario="bound_synthetic_control",
        )
        session.commit()
        assert integrated.persist.outcome == PaperPairOutcome.CREATED
        gateway_calls_first = integrated.gateway_calls_before_persist
        assert gateway_calls_first >= 6

    q0, q1 = test_ids
    script = f'''
from sqlalchemy.orm import Session
import app.models  # noqa: F401
from app.db.session import create_database_engine
from app.jee_advanced.production_orchestration import run_labeled_synthetic_pair_integration
from app.orchestration.gateway.fake import FakeGenerationGateway

engine = create_database_engine("sqlite:///{db_path}")
with Session(engine) as session:
    gw = FakeGenerationGateway()
    result = run_labeled_synthetic_pair_integration(
        session,
        gw,
        organization_id="org-int",
        institution_id="inst-int",
        exam_version_id="{version_id}",
        question_ids=("{q0}", "{q1}"),
        idempotency_key="idem-p47",
        pair_correlation_id="pair-p47",
        scenario="bound_synthetic_control",
    )
    session.commit()
    print(result.persist.outcome)
    print(result.gateway_calls)
    print(len(result.persist.test_definition_ids))
'''
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == "replayed"
    assert lines[1] == "0"
    assert lines[2] == "2"
    create_database_engine.cache_clear()


def test_prod47_03_historical_by_academic_year_column(tmp_path: Path) -> None:
    session = _session(tmp_path)
    for year in (2023, 2025):
        session.add(
            Source(
                source_type="official_paper",
                title=f"JEE {year}",
                url="https://example.invalid",
                authority="Synthetic",
                country="IN",
                board_or_exam="jee_advanced",
                academic_year=str(year),
                metadata_json={"d12_core_test_fixture": True},
            )
        )
    session.commit()
    by_year = list_historical_sources_by_year(session)
    assert len(by_year[2023]) == 1
    assert len(by_year[2024]) == 0
    assert by_year[2023][0].academic_year == "2023"
    session.close()


def test_prod47_04_scope_ledger_unchanged() -> None:
    counts = load_repo_scope_counts()
    assert counts["PASS"] == 0
    assert counts["PARTIAL"] == 32
    assert counts["SOURCE_PENDING"] == 3
    assert counts["NOT_STARTED"] == 1
    assert counts["TOTAL"] == 36