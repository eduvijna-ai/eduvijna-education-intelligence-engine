from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
from app.models.enums import SourceType
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import Source, SourceRevision
from app.models.tenancy import Institution, Organization
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.diagnostic_audit import persist_diagnostic_item_audit
from app.orchestration.nodes.root_cause import root_cause_enrich_node
from app.orchestration.state import OrchestrationGraphState
from app.paper_distribution.contracts import PaperDistributionRequest, PaperItemInput
from app.paper_distribution.target_policy_registry import (
    PAPER_TARGET_POLICY_VERSION,
    ensure_paper_target_policy_configured,
)
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext

ORG_A = "d9a0a0a0-a0a0-4000-8000-000000000001"
INST_A = "d9b0b0b0-b0b0-4000-8000-000000000002"
INST_B = "d9c0c0c0-c0c0-4000-8000-000000000003"


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-r9.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_institution_source_cannot_carry_official_authority(tmp_path: Path) -> None:
    from app.prerequisite_intelligence.authority import (
        _revision_record,
        revision_permits_official_authority,
    )

    session = _session(tmp_path)
    session.add(Organization(id=ORG_A, code="r9-org", name="R9 Org"))
    session.flush()
    session.add(Institution(id=INST_A, organization_id=ORG_A, code="r9-inst", name="Inst"))
    session.flush()
    source = Source(
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="Institution edge source",
        organization_id=ORG_A,
        institution_id=INST_A,
    )
    session.add(source)
    session.flush()
    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum="c" * 64,
        source_snapshot_checksum="d" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_checksum="c" * 64,
        metadata_json={},
    )
    session.add(revision)
    session.commit()
    record = _revision_record(revision)
    assert not revision_permits_official_authority(record)


def test_synthetic_mapping_blocked_in_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.prerequisite_intelligence.fixtures import (
        load_day10_fixture_snapshot,
        seed_day10_prerequisite_fixture,
    )

    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    monkeypatch.setattr(
        "app.root_cause_intelligence.service.validate_graph_snapshot_attestation",
        lambda *args, **kwargs: ([], [], False),
    )
    monkeypatch.setattr(
        "app.root_cause_intelligence.service.verify_root_cause_trusted_context",
        lambda *args, **kwargs: ([], []),
    )
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-1",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref="audit-ref",
    )
    result = RootCauseIntelligenceService().analyze(
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
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
            allowed_source_revision_ids=[ctx["source_revision_id"]],
            orchestration_run_id="run-r9",
            orchestration_request_hash="hash-r9",
        ),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert result.hypotheses == []
    assert RootCauseIssueCode.CONFLICTING_EVIDENCE in result.issue_codes
    assert result.verdict_status == RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE


def test_persisted_day9_scope_blocks_cross_tenant_replay(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.add(Organization(id=ORG_A, code="r9-org2", name="R9 Org"))
    session.flush()
    session.add_all(
        [
            Institution(id=INST_A, organization_id=ORG_A, code="r9-a", name="A"),
            Institution(id=INST_B, organization_id=ORG_A, code="r9-b", name="B"),
        ]
    )
    session.flush()
    deps = MagicMock()
    deps.session = session
    deps.control_session = session
    state: OrchestrationGraphState = {
        "run_id": "run-scope",
        "request_hash": "hash-scope",
    }
    audit_id = persist_diagnostic_item_audit(
        deps,
        state,
        item_id="item-scope",
        attempt=1,
        status="pass",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        prompt_version=None,
        misconception_codes=["MATH.ADD.WHOLE.OFF_BY_ONE_LOW"],
        source_revision_ids=[],
        issue_codes=[],
        scope_metadata={"organization_id": ORG_A, "institution_id": INST_A},
        option_traces=[
            {
                "option_key": "A",
                "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "validation_status": DiagnosticValidationStatus.PASS.value,
            }
        ],
    )
    session.commit()
    event = session.get(OrchestrationAuditEvent, audit_id)
    assert event is not None
    assert (event.payload_json or {}).get("scope", {}).get("institution_id") == INST_A
    from app.prerequisite_intelligence.fixtures import (
        load_day10_fixture_snapshot,
        seed_day10_prerequisite_fixture,
    )

    ctx = seed_day10_prerequisite_fixture(session)
    snapshot = load_day10_fixture_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-scope",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    result = RootCauseIntelligenceService().analyze(
        RootCauseDiagnosticRequest(
            item_id="item-scope",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            tag=OptionDiagnosticTag(
                item_id="item-scope",
                option_key="A",
                is_correct=False,
                misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                validation_status=DiagnosticValidationStatus.PASS,
                taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            ),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
            institution_id=INST_B,
            organization_id=ORG_A,
            orchestration_run_id="run-scope",
            orchestration_request_hash="hash-scope",
        ),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    assert result.hypotheses == []


def test_mandatory_target_enforced_when_omitted_from_request(tmp_path: Path) -> None:
    from sqlalchemy import select

    from app.models.education_intelligence import PolicyRegistryEntry
    from app.paper_distribution.target_policy_registry import paper_targets_authorized

    session = _session(tmp_path)
    ensure_paper_target_policy_configured(session)
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == "paper_distribution",
            PolicyRegistryEntry.version == PAPER_TARGET_POLICY_VERSION,
        )
    )
    assert row is not None
    row.payload_json = {
        **(row.payload_json or {}),
        "mandatory_cognitive_exact_percent": {"remember": 100.0},
    }
    session.flush()
    from app.paper_distribution.contracts import DistributionTarget

    paper = PaperDistributionRequest(
        paper_id="mandatory-omitted",
        requested_count=1,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=50.0),
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
    ok, path = paper_targets_authorized(session, paper, version=PAPER_TARGET_POLICY_VERSION)
    assert ok is False
    assert path is not None


def test_root_cause_replay_guard_runs_when_feature_enabled(tmp_path: Path) -> None:
    from app.prerequisite_intelligence.fixtures import seed_day10_prerequisite_fixture

    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    deps = MagicMock()
    deps.session = session
    deps.control_session = session
    request = OrchestrationRequest(
        idempotency_key="replay-r9-key-01",
        retrieval_profile_version="default@v1",
        metadata_json={"root_cause_enrichment_enabled": True},
        curriculum_version_id=ctx["curriculum_version_id"],
    )
    state: OrchestrationGraphState = {
        "run_id": "run-replay-r9",
        "request_hash": "hash-replay-r9",
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
            query_id="replay-r9",
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
