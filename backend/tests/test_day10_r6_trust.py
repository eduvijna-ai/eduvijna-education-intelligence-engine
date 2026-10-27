from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.knowledge_intelligence.contracts import KnowledgeContextPack, KnowledgeEvidenceItem
from app.models.education_intelligence import ValidationAuditRun
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.graph import build_orchestration_graph
from app.orchestration.fixtures import build_day8_test_service
from app.orchestration.root_cause_trust import option_allowed_source_revision_ids
from app.paper_distribution.audit import persist_paper_distribution_audit
from app.paper_distribution.contracts import PaperDistributionRequest, PaperItemInput
from app.paper_distribution.enums import PaperDistributionIssueCode
from app.paper_distribution.evaluator import (
    evaluate_paper_distribution,
    evaluate_paper_distribution_with_session,
)
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.fixtures import build_demo_ten_question_paper
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    seed_paper_target_policy_registry,
)
from app.paper_distribution.trusted_validation import PaperDay6TrustContext
from app.prerequisite_intelligence.fixtures import (
    load_day10_fixture_snapshot,
    seed_day10_prerequisite_fixture,
)
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-r6.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _persist_day6_passing_run(session: Session) -> tuple[str, dict]:
    ctx = seed_cbse_fixture_curriculum(session)
    session.flush()
    item = positive_cbse_item(ctx)
    service = EducationIntelligenceValidationService(session)
    summary = service.validate_item(item, board_code="cbse", persist=True, actor_id="actor-1")
    session.flush()
    record = session.scalars(
        select(ValidationAuditRun).where(ValidationAuditRun.run_id == summary.run_id)
    ).first()
    assert record is not None
    validated = (record.metadata_json or {}).get("validated_items", [])[0]
    return str(record.id), validated


def test_paper_distribution_audit_cannot_pose_as_day6(tmp_path: Path) -> None:
    session = _session(tmp_path)
    seed_paper_target_policy_registry(session)
    request = build_demo_ten_question_paper()
    result = evaluate_paper_distribution(
        request,
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
        data_session=session,
    )
    paper_audit_id = persist_paper_distribution_audit(session, request, result)
    session.flush()
    trust = PaperDay6TrustContext.from_validation_run(paper_audit_id)
    checked = evaluate_paper_distribution(
        request,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        data_session=session,
        execution_context=PaperExecutionContext(institution_id="inst-a"),
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in checked.issue_codes


def test_day6_run_for_item_a_cannot_authorize_item_b(tmp_path: Path) -> None:
    session = _session(tmp_path)
    seed_paper_target_policy_registry(session)
    run_id, validated = _persist_day6_passing_run(session)
    session.commit()
    paper = PaperDistributionRequest(
        paper_id="wrong-item",
        requested_count=1,
        items=[
            PaperItemInput(
                item_id="item-b-not-in-run",
                marks=1.0,
                cognitive_level=str(validated.get("declared_cognitive_level") or "remember"),
                competency_codes=list(validated.get("competency_codes") or ["knowledge"]),
                day6_validated=True,
            )
        ],
    )
    trust = PaperDay6TrustContext.from_validation_run(run_id)
    inst = validated.get("institution_id") or "inst-a"
    result = evaluate_paper_distribution(
        paper,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        data_session=session,
        execution_context=PaperExecutionContext(institution_id=inst),
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes


def test_day6_validated_item_positive_with_matching_tags(tmp_path: Path) -> None:
    session = _session(tmp_path)
    seed_paper_target_policy_registry(session)
    run_id, validated = _persist_day6_passing_run(session)
    session.commit()
    item_id = str(validated["item_id"])
    paper = PaperDistributionRequest(
        paper_id="positive",
        requested_count=1,
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
        items=[
            PaperItemInput(
                item_id=item_id,
                marks=1.0,
                cognitive_level=str(validated.get("declared_cognitive_level")),
                competency_codes=list(validated.get("competency_codes") or []),
                primary_competency_code=(validated.get("competency_codes") or ["knowledge"])[0],
                day6_validated=True,
                metadata_json={"day6_input_hash": validated["input_hash"]},
            )
        ],
        cognitive_targets=[],
    )
    trust = PaperDay6TrustContext.from_validation_run(run_id)
    inst = validated.get("institution_id")
    result = evaluate_paper_distribution(
        paper,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        data_session=session,
        execution_context=PaperExecutionContext(institution_id=inst),
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION not in result.issue_codes


def test_cognitive_mismatch_on_day6_record_fails(tmp_path: Path) -> None:
    session = _session(tmp_path)
    seed_paper_target_policy_registry(session)
    run_id, validated = _persist_day6_passing_run(session)
    session.commit()
    paper = PaperDistributionRequest(
        paper_id="mismatch",
        requested_count=1,
        items=[
            PaperItemInput(
                item_id=str(validated["item_id"]),
                marks=1.0,
                cognitive_level="evaluate",
                competency_codes=list(validated.get("competency_codes") or ["knowledge"]),
                day6_validated=True,
            )
        ],
    )
    trust = PaperDay6TrustContext.from_validation_run(run_id)
    result = evaluate_paper_distribution(
        paper,
        day6_trust=trust,
        execution_mode=TrustExecutionMode.PRODUCTION,
        data_session=session,
        execution_context=PaperExecutionContext(institution_id=validated.get("institution_id")),
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes


def test_forged_loader_attested_graph_zero_hypotheses_production(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    forged = snapshot.model_copy(
        update={
            "metadata_json": {
                **snapshot.metadata_json,
                "loader_attested": True,
                "loader_scope": {"institution_id": "other-inst"},
            }
        }
    )
    service = RootCauseIntelligenceService()
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=OptionDiagnosticTag(
                item_id="item-1",
                option_key="A",
                is_correct=False,
                misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                validation_status=DiagnosticValidationStatus.PASS,
                taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            ),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=forged,
            target_concept_code="multi-step-addition",
            institution_id="tenant-a",
        ),
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.hypotheses == []
    assert RootCauseIssueCode.FOREIGN_TENANT in result.issue_codes or (
        RootCauseIssueCode.MISSING_GRAPH in result.issue_codes
    )


def test_option_sources_empty_refs_no_broadening() -> None:
    context = KnowledgeContextPack.model_construct(
        evidence=[
            KnowledgeEvidenceItem(
                source_id="s",
                source_revision_id="rev-a",
                source_revision_checksum="a" * 64,
                binding_id="b",
                trust_tier="official",
                authority_label="x",
                title="t",
                locator="l",
                snippet="sn",
                retrieval_score=1.0,
                retrieval_rank=1,
                anythingllm_workspace="w",
                anythingllm_document_id="d",
                citation_label="cite-a",
            )
        ]
    )
    draft = {"source_revision_ids": ["rev-a", "rev-b"]}
    assert option_allowed_source_revision_ids(draft, context, {"evidence_refs": []}) == []


def test_option_unknown_citation_fails_closed() -> None:
    context = KnowledgeContextPack.model_construct(
        evidence=[
            KnowledgeEvidenceItem(
                source_id="s",
                source_revision_id="rev-a",
                source_revision_checksum="a" * 64,
                binding_id="b",
                trust_tier="official",
                authority_label="x",
                title="t",
                locator="l",
                snippet="sn",
                retrieval_score=1.0,
                retrieval_rank=1,
                anythingllm_workspace="w",
                anythingllm_document_id="d",
                citation_label="cite-a",
            )
        ]
    )
    draft = {"source_revision_ids": ["rev-a"]}
    mixed = {"evidence_refs": ["cite-a", "cite-forged"]}
    assert option_allowed_source_revision_ids(draft, context, mixed) == []


def test_paper_audit_same_content_isolated_by_execution_context(tmp_path: Path) -> None:
    session = _session(tmp_path)
    request = build_demo_ten_question_paper()
    ref_a = evaluate_paper_distribution_with_session(
        session,
        request,
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
        execution_context=PaperExecutionContext(institution_id="inst-a", actor_id="actor-a"),
    ).audit_ref
    ref_b = evaluate_paper_distribution_with_session(
        session,
        request,
        day6_trust=PaperDay6TrustContext.synthetic_fixture_harness(),
        execution_mode=TrustExecutionMode.SYNTHETIC_FIXTURE,
        execution_context=PaperExecutionContext(institution_id="inst-b", actor_id="actor-b"),
    ).audit_ref
    session.commit()
    assert ref_a != ref_b


def test_orchestration_graph_compiles_with_root_cause_node(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _, service = build_day8_test_service(session)
    graph = build_orchestration_graph(
        service.dependencies, checkpointer=service.managed_checkpointer.saver
    )
    assert graph is not None
    session.close()


def test_day9_evidence_ref_mismatch_blocks_trust(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    audit_id = "00000000-0000-4000-8000-000000000002"
    session.add(
        OrchestrationAuditEvent(
            id=audit_id,
            run_id="run-test",
            request_hash="hash",
            node_name="diagnostic_item",
            status="pass",
            attempt=1,
            payload_json={
                "item_id": "item-1",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "option_traces": [
                    {
                        "option_key": "A",
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                        "evidence_refs": ["[CIT-1]"],
                    }
                ],
            },
        )
    )
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext

    service = RootCauseIntelligenceService()
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-1",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="item-1",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=OptionDiagnosticTag(
                item_id="item-1",
                option_key="A",
                is_correct=False,
                misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                validation_status=DiagnosticValidationStatus.PASS,
                taxonomy_version=DEFAULT_TAXONOMY_VERSION,
                evidence_refs=["[CIT-2]"],
            ),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        ),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    assert result.verdict_status == RootCauseVerdictStatus.REVIEW_REQUIRED
