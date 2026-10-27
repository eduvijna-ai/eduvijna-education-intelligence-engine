from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.education_intelligence.fixtures import positive_cbse_item, seed_cbse_fixture_curriculum
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
from app.models.curriculum import (
    ConceptPrerequisite,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    EducationFramework,
)
from app.models.education_intelligence import ValidationAuditRun
from app.models.enums import CurriculumNodeType, CurriculumStatus, SourceType
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import Source, SourceRevision
from app.models.tenancy import Institution, Organization
from app.orchestration.nodes.root_cause import root_cause_enrich_node
from app.orchestration.state import OrchestrationGraphState
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import PaperDistributionIssueCode
from app.paper_distribution.evaluator import evaluate_paper_distribution_with_session
from app.paper_distribution.execution_context import PaperExecutionContext
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
    paper_targets_authorized,
)
from app.paper_distribution.trusted_validation import PaperDay6TrustContext
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.prerequisite_intelligence.enums import EdgeProvenanceClass
from app.prerequisite_intelligence.loader import load_prerequisite_graph_snapshot
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext

ORG_A = "a0a0a0a0-a0a0-4000-8000-000000000001"
INST_A = "b0b0b0b0-b0b0-4000-8000-000000000002"
INST_B = "c0c0c0c0-c0c0-4000-8000-000000000003"


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-r8.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_production_institution_graph(session: Session) -> dict[str, str]:
    session.add(Organization(id=ORG_A, code="r8-org", name="R8 Org"))
    session.flush()
    session.add_all(
        [
            Institution(id=INST_A, organization_id=ORG_A, code="r8-inst-a", name="Inst A"),
            Institution(id=INST_B, organization_id=ORG_A, code="r8-inst-b", name="Inst B"),
        ]
    )
    session.flush()
    source = Source(
        source_type=SourceType.OFFICIAL_SYLLABUS.value,
        title="R8 official prerequisite source",
    )
    framework = EducationFramework(code="r8-fw", name="R8 Framework", country="IN")
    pack = CurriculumPack(code="r8-pack", name="R8 Pack", country="IN", framework=framework)
    version = CurriculumVersion(
        curriculum_pack=pack,
        version_code="r8-2026",
        status=CurriculumStatus.ACTIVE.value,
        metadata_json={},
    )
    subject = CurriculumNode(
        curriculum_version=version,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics",
        title="Mathematics",
    )
    counting = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="counting-sequence",
        title="Counting",
        metadata_json={"grade_year_code": "grade-2", "subject_code": "mathematics"},
    )
    multi_add = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="multi-step-addition",
        title="Multi-step addition",
        metadata_json={"grade_year_code": "grade-4", "subject_code": "mathematics"},
    )
    session.add_all([source, framework, pack, version, subject, counting, multi_add])
    session.flush()
    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum="a" * 64,
        source_snapshot_checksum="b" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_checksum="a" * 64,
        metadata_json={},
    )
    revision.curriculum_versions.append(version)
    version.sources.append(source)
    session.add(revision)
    session.flush()

    def official_edge(prereq: CurriculumNode, target: CurriculumNode) -> ConceptPrerequisite:
        return ConceptPrerequisite(
            prerequisite_concept=prereq,
            target_concept=target,
            weight=0.9,
            metadata_json={
                "provenance_class": EdgeProvenanceClass.OFFICIAL.value,
                "source_revision_id": revision.id,
                "source_locator": f"{prereq.code}->{target.code}",
            },
        )

    session.add(official_edge(counting, multi_add))
    session.flush()
    return {
        "curriculum_version_id": version.id,
        "source_revision_id": revision.id,
        "multi_add_concept_id": multi_add.id,
        "organization_id": ORG_A,
        "institution_id": INST_A,
    }


def _load_snapshot(session: Session, ctx: dict[str, str]) -> object:
    scope = PrerequisiteGraphScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    return load_prerequisite_graph_snapshot(session, scope)


def _day9_audit(session: Session, ctx: dict[str, str], *, audit_id: str) -> None:
    session.add(
        OrchestrationAuditEvent(
            id=audit_id,
            run_id="run-r8",
            request_hash="hash-r8",
            node_name="diagnostic_item",
            status="pass",
            attempt=1,
            source_revision_ids_json={"ids": [ctx["source_revision_id"]]},
            payload_json={
                "item_id": "item-r8",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "scope": {
                    "organization_id": ctx["organization_id"],
                    "institution_id": ctx["institution_id"],
                },
                "option_traces": [
                    {
                        "option_key": "A",
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                        "evidence_refs": [],
                    }
                ],
            },
        )
    )


def _root_cause_request(
    ctx: dict[str, str],
    snapshot: object,
    *,
    institution_id: str | None,
    metadata_json: dict | None = None,
) -> RootCauseDiagnosticRequest:
    meta = dict(snapshot.metadata_json or {})
    if metadata_json:
        meta = {**meta, **metadata_json}
    forged_snapshot = snapshot.model_copy(update={"metadata_json": meta})
    return RootCauseDiagnosticRequest(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        tag=OptionDiagnosticTag(
            item_id="item-r8",
            option_key="A",
            is_correct=False,
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            validation_status=DiagnosticValidationStatus.PASS,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        ),
        curriculum_version_id=ctx["curriculum_version_id"],
        graph_snapshot=forged_snapshot,
        target_concept_code="multi-step-addition",
        organization_id=ctx["organization_id"],
        institution_id=institution_id,
        allowed_source_revision_ids=[ctx["source_revision_id"]],
        orchestration_run_id="run-r8",
        orchestration_request_hash="hash-r8",
    )


def test_forged_loader_scope_with_tenant_b_request_zero_hypotheses(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    audit_id = "00000000-0000-4000-8000-000000000008"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = RootCauseIntelligenceService().analyze(
        _root_cause_request(
            ctx,
            snapshot,
            institution_id=INST_B,
            metadata_json={
                "loader_scope": {
                    "organization_id": ORG_A,
                    "institution_id": INST_B,
                    "subject_code": "mathematics",
                    "grade_year_code": "grade-4",
                }
            },
        ),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.hypotheses == []
    assert (
        RootCauseIssueCode.FOREIGN_TENANT in result.issue_codes
        or RootCauseIssueCode.MISSING_GRAPH in result.issue_codes
    )


def test_private_scope_blank_request_tenant_fails(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    audit_id = "00000000-0000-4000-8000-000000000009"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = RootCauseIntelligenceService().analyze(
        _root_cause_request(ctx, snapshot, institution_id=None),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.hypotheses == []
    assert (
        RootCauseIssueCode.FOREIGN_TENANT in result.issue_codes
        or RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    )


def test_matching_tenant_production_graph_positive(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    audit_id = "00000000-0000-4000-8000-00000000000a"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = RootCauseIntelligenceService().analyze(
        _root_cause_request(ctx, snapshot, institution_id=INST_A),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert RootCauseIssueCode.FOREIGN_TENANT not in result.issue_codes
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION not in result.issue_codes


def test_production_requires_orchestration_run_and_hash(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    audit_id = "00000000-0000-4000-8000-00000000000b"
    _day9_audit(session, ctx, audit_id=audit_id)
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    base = _root_cause_request(ctx, snapshot, institution_id=INST_A)
    missing_run = base.model_copy(update={"orchestration_run_id": None})
    result = RootCauseIntelligenceService().analyze(
        missing_run,
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    assert result.hypotheses == []


def _persist_day6(session: Session, *, ctx: dict[str, str] | None = None) -> tuple[str, dict]:
    if ctx is None:
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


def _paper_item_from_validated(validated: dict) -> PaperItemInput:
    return PaperItemInput(
        item_id=str(validated["item_id"]),
        marks=1.0,
        cognitive_level=str(validated.get("declared_cognitive_level")),
        competency_codes=list(validated.get("competency_codes") or []),
        primary_competency_code=(validated.get("competency_codes") or ["knowledge"])[0],
        day6_validated=True,
        metadata_json={
            "day6_input_hash": validated["input_hash"],
            "curriculum_version_id": validated.get("curriculum_version_id"),
            "grade_year_code": validated.get("grade_year_code"),
            "medium_code": validated.get("medium_code"),
            "subject_code": validated.get("subject_code"),
            "learning_outcome_ids": list(validated.get("learning_outcome_ids") or []),
        },
    )


def test_two_day6_runs_same_paper_distinct_audit_run_ids(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    cbse_ctx = seed_cbse_fixture_curriculum(session)
    session.flush()
    run_a, validated = _persist_day6(session, ctx=cbse_ctx)
    run_b, _ = _persist_day6(session, ctx=cbse_ctx)
    session.commit()
    paper = PaperDistributionRequest(
        paper_id="dual-day6",
        requested_count=1,
        items=[_paper_item_from_validated(validated)],
    )
    inst = validated.get("institution_id")
    ctx = PaperExecutionContext(institution_id=inst, actor_id="actor-a")
    first = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=PaperDay6TrustContext.from_validation_run(run_a),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=ctx,
    )
    second = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=PaperDay6TrustContext.from_validation_run(run_b),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=ctx,
    )
    assert first.audit_ref != second.audit_ref
    rec_a = session.get(ValidationAuditRun, first.audit_ref)
    rec_b = session.get(ValidationAuditRun, second.audit_ref)
    assert rec_a is not None and rec_b is not None
    assert rec_a.run_id != rec_b.run_id
    assert len(rec_a.run_id) <= 64 and len(rec_b.run_id) <= 64


def test_generic_cognitive_targets_not_rejected_by_demo_defaults(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    request = PaperDistributionRequest(
        paper_id="generic-targets",
        requested_count=1,
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=30.0),
            DistributionTarget(dimension="cognitive", key="understand", exact_percent=20.0),
        ],
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            )
        ],
    )
    ok, path = paper_targets_authorized(session, request, version=PAPER_TARGET_POLICY_VERSION)
    assert ok is True
    assert path is None


def test_mandatory_policy_percent_still_enforced(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    from app.models.education_intelligence import PolicyRegistryEntry

    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == "paper_distribution",
            PolicyRegistryEntry.version == PAPER_TARGET_POLICY_VERSION,
        )
    )
    assert row is not None
    row.payload_json = {
        **(row.payload_json or {}),
        "mandatory_cognitive_exact_percent": {"remember": 20.0},
    }
    session.flush()
    request = PaperDistributionRequest(
        paper_id="mandatory",
        requested_count=1,
        target_policy_version=PAPER_TARGET_POLICY_VERSION,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=30.0),
        ],
        items=[
            PaperItemInput(
                item_id="q1",
                marks=1.0,
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=True,
            )
        ],
    )
    ok, path = paper_targets_authorized(session, request, version=PAPER_TARGET_POLICY_VERSION)
    assert ok is False
    assert path is not None


def test_missing_day6_scope_metadata_fails_production(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    run_id, validated = _persist_day6(session)
    session.commit()
    paper = PaperDistributionRequest(
        paper_id="missing-scope",
        requested_count=1,
        items=[
            PaperItemInput(
                item_id=str(validated["item_id"]),
                marks=1.0,
                cognitive_level=str(validated.get("declared_cognitive_level")),
                competency_codes=list(validated.get("competency_codes") or []),
                day6_validated=True,
                metadata_json={"day6_input_hash": validated["input_hash"]},
            )
        ],
    )
    result = evaluate_paper_distribution_with_session(
        session,
        paper,
        day6_trust=PaperDay6TrustContext.from_validation_run(run_id),
        execution_mode=TrustExecutionMode.PRODUCTION,
        execution_context=PaperExecutionContext(),
    )
    assert PaperDistributionIssueCode.UNTRUSTED_DAY6_ASSERTION in result.issue_codes


def test_root_cause_replay_skips_duplicate_item_option(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from app.orchestration.contracts import OrchestrationRequest
    from app.prerequisite_intelligence.fixtures import seed_day10_prerequisite_fixture

    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    deps = MagicMock()
    deps.session = session
    deps.control_session = session
    request = OrchestrationRequest(
        idempotency_key="replay-key-001",
        retrieval_profile_version="default@v1",
        metadata_json={"root_cause_enrichment_enabled": True},
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    state: OrchestrationGraphState = {
        "run_id": "run-replay",
        "request_hash": "hash-replay",
        "request": request.model_dump(mode="json"),
        "root_cause_results": [
            {
                "item_id": "item-1",
                "option_key": "A",
                "verdict_status": "review_required",
            }
        ],
        "diagnostic_results": [
            {
                "item_id": "item-1",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "option_tags": [
                    {
                        "option_key": "A",
                        "is_correct": False,
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                    }
                ],
            }
        ],
        "resolved_scope": {
            "curriculum_version_id": ctx["curriculum_version_id"],
            "organization_id": ctx["organization_id"],
            "institution_id": ctx["institution_id"],
            "subject_code": "mathematics",
            "concept_codes": ["multi-step-addition"],
        },
        "draft_items": [
            {
                "item_id": "item-1",
                "concept_codes": ["multi-step-addition"],
                "source_revision_ids": [ctx["source_revision_id"]],
            }
        ],
        "deterministic_validation": [{"item_id": "item-1", "blocking": False}],
        "knowledge_context": KnowledgeContextPack(
            query_id="replay-r8",
            query_text="replay",
            retrieval_profile_version="ki-retrieval-v1",
            evidence=[],
            citations=[],
            scope=AppliedKnowledgeScope(curriculum_version_id=ctx["curriculum_version_id"]),
            warnings=[],
            bounded_text="",
        ).model_dump(mode="json"),
    }
    update = root_cause_enrich_node(state, deps)
    assert len(update.get("root_cause_results") or []) == 1
