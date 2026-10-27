from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from day10_source_lifecycle import ensure_genuine_source_content_approval
from sqlalchemy import func, select
from test_day10_r8_trust import (
    INST_A,
    _day9_audit,
    _load_snapshot,
    _root_cause_request,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r10_trust import _persist_day6_item
from test_day10_r11_trust import (
    _APPROVED_MAPPING_OVERLAY_BASE,
    _MAPPING_SOURCE_LOCATOR,
    _approve_revision_mapping_binding,
)

from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.common.trust_execution import TrustExecutionMode
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.education_intelligence.fixtures import seed_cbse_fixture_curriculum
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import SourceAuditEvent, SourceRevision
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.diagnostic_audit import persist_diagnostic_item_audit
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import (
    build_diagnostic_orchestration_request,
    seed_day8_fixtures,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.nodes.root_cause import root_cause_enrich_node
from app.orchestration.state import OrchestrationGraphState
from app.prerequisite_intelligence.authority import load_revision_record
from app.root_cause_intelligence.enums import RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
    mapping_evidence_checksum,
    source_content_checksum,
)
from app.root_cause_intelligence.mapping_claim_authority import (
    MAPPING_CLAIM_APPROVED_EVENT,
    revoke_root_cause_mapping_claim,
)
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


def test_post_hoc_mapping_metadata_without_claim_audit_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    revision_id = ctx["source_revision_id"]
    ensure_genuine_source_content_approval(
        session,
        tmp_path,
        revision_id,
        source_locator=_MAPPING_SOURCE_LOCATOR,
    )
    revision = session.get(SourceRevision, revision_id)
    assert revision is not None
    record = load_revision_record(session, revision_id)
    assert record is not None
    content_checksum = source_content_checksum(record)
    assert content_checksum
    evidence_checksum = mapping_evidence_checksum(
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        candidate_concept_codes=["whole-number-addition", "multi-step-addition"],
        source_locator=_MAPPING_SOURCE_LOCATOR,
        mapping_registry_version="root-cause-mapping@v1",
        source_revision_id=revision_id,
        source_content_checksum=content_checksum,
    )
    revision.metadata_json = {
        **(revision.metadata_json or {}),
        "root_cause_mapping_bindings": [
            {
                "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "candidate_concept_codes": ["whole-number-addition", "multi-step-addition"],
                "source_locator": _MAPPING_SOURCE_LOCATOR,
                "mapping_registry_version": "root-cause-mapping@v1",
                "source_revision_id": revision_id,
                "source_content_checksum": content_checksum,
                "mapping_evidence_checksum": evidence_checksum,
                "approval_status": "active",
                "approval_fingerprint": revision.approval_fingerprint,
                "approved_by": revision.approved_by,
            }
        ],
    }
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={
                "overlays": [
                    {
                        **_APPROVED_MAPPING_OVERLAY_BASE,
                        "source_locator": _MAPPING_SOURCE_LOCATOR,
                        "source_revision_ids": [revision_id],
                        "mapping_evidence_checksum": evidence_checksum,
                    }
                ]
            },
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000031"
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
    assert result.hypotheses == []
    assert result.verdict_status in {
        RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE,
        RootCauseVerdictStatus.FAIL,
    }


def test_revoked_mapping_claim_blocks_production(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    mapping_overlay = _approve_revision_mapping_binding(
        session, tmp_path, ctx["source_revision_id"]
    )
    approved_event = session.scalar(
        select(SourceAuditEvent).where(
            SourceAuditEvent.source_revision_id == ctx["source_revision_id"],
            SourceAuditEvent.event_type == MAPPING_CLAIM_APPROVED_EVENT,
        )
    )
    assert approved_event is not None
    claim_id = str((approved_event.payload_json or {}).get("claim_id") or "")
    assert claim_id
    revoke_root_cause_mapping_claim(
        session,
        revision_id=ctx["source_revision_id"],
        claim_id=claim_id,
        actor_id="curator-revoke-test",
    )
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000032"
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
    assert result.hypotheses == []


def test_day6_day9_writer_root_cause_enrich_production_pass(tmp_path: Path) -> None:
    from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
    from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack

    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    cbse = seed_cbse_fixture_curriculum(session)
    session.flush()
    day6_run_id, validated = _persist_day6_item(session, cbse, "item-r15-chain")
    assert validated.get("competency_codes")
    mapping_overlay = _approve_revision_mapping_binding(
        session, tmp_path, ctx["source_revision_id"]
    )
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    session.commit()
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    revision_id = ctx["source_revision_id"]
    deps = MagicMock()
    deps.session = session
    deps.control_session = session
    request = OrchestrationRequest(
        idempotency_key="r15-chain-key",
        retrieval_profile_version="default@v1",
        metadata_json={"root_cause_enrichment_enabled": True},
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    state: OrchestrationGraphState = {
        "run_id": "run-r15-chain",
        "request_hash": "hash-r15-chain",
        "request": request.model_dump(mode="json"),
        "resolved_scope": {
            "curriculum_version_id": ctx["curriculum_version_id"],
            "organization_id": ctx["organization_id"],
            "institution_id": ctx["institution_id"],
            "grade_year_code": "grade-4",
            "subject_code": "mathematics",
            "concept_codes": ["multi-step-addition"],
        },
        "draft_items": [
            {
                "item_id": "item-r15-chain",
                "concept_codes": ["multi-step-addition"],
                "source_revision_ids": [revision_id],
            }
        ],
        "diagnostic_validation": [{"item_id": "item-r15-chain", "blocking": False}],
        "deterministic_validation": [
            {
                "item_id": "item-r15-chain",
                "blocking": False,
                "day6_validation_run_id": day6_run_id,
                "learning_outcome_ids": [cbse["learning_outcome_id"]],
            }
        ],
        "diagnostic_results": [],
        "node_attempts": {},
    }
    audit_ref = persist_diagnostic_item_audit(
        deps,
        state,
        item_id="item-r15-chain",
        attempt=1,
        status="pass",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        prompt_version="diag@v1",
        misconception_codes=["MATH.ADD.WHOLE.OFF_BY_ONE_LOW"],
        source_revision_ids=[revision_id],
        issue_codes=[],
        scope_metadata={
            "organization_id": ctx["organization_id"],
            "institution_id": ctx["institution_id"],
        },
        option_traces=[
            {
                "option_key": "A",
                "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "validation_status": "pass",
                "source_revision_ids": [revision_id],
                "evidence_refs": ["cite-r15"],
            }
        ],
    )
    state["diagnostic_results"] = [
            {
                "item_id": "item-r15-chain",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "audit_refs": [audit_ref],
                "option_tags": [
                    {
                        "option_key": "A",
                        "is_correct": False,
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                        "evidence_refs": ["cite-r15"],
                    }
                ],
            }
        ]
    state["knowledge_context"] = KnowledgeContextPack(
            query_id="r15-chain",
            query_text="addition",
            retrieval_profile_version="ki-retrieval-v1",
            evidence=[
                {
                    "source_id": ctx["source_id"],
                    "source_revision_id": revision_id,
                    "source_revision_checksum": revision.checksum,
                    "binding_id": "bind-r15",
                    "trust_tier": "official_primary",
                    "authority_label": "official",
                    "title": "R8 official prerequisite source",
                    "locator": _MAPPING_SOURCE_LOCATOR,
                    "snippet": "snippet",
                    "retrieval_score": 1.0,
                    "retrieval_rank": 1,
                    "anythingllm_workspace": "ws",
                    "anythingllm_document_id": "doc",
                    "citation_label": "cite-r15",
                }
            ],
            citations=[],
            scope=AppliedKnowledgeScope(curriculum_version_id=ctx["curriculum_version_id"]),
            warnings=[],
            bounded_text="",
        ).model_dump(mode="json")
    session.commit()
    update = root_cause_enrich_node(state, deps)
    results = update.get("root_cause_results") or []
    assert results
    assert results[0].get("verdict_status") == RootCauseVerdictStatus.PASS.value
    assert results[0].get("hypotheses")
    assert validated.get("declared_cognitive_level")
    assert validated.get("competency_codes")


def test_persistent_checkpoint_hitl_resume_no_extra_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "r15-orch.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from app.core.config import get_settings
    from app.db.session import create_database_engine

    get_settings.cache_clear()
    create_database_engine.cache_clear()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.base import Base
    from app.db.session import enable_sqlite_foreign_keys

    engine = create_engine(f"sqlite:///{db_path}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)
    gateway = FakeGenerationGateway()
    ki_adapter = FakeAnythingLLMAdapter()
    ctx = seed_day8_fixtures(session, adapter=ki_adapter)
    service = build_orchestration_service(
        session,
        gateway=gateway,
        knowledge_adapter=ki_adapter,
        memory_checkpointer=False,
        force_fake=True,
    )
    request = build_diagnostic_orchestration_request(
        ctx,
        scenario="human_review",
        idempotency_key="d10-r15-hitl-checkpoint",
        requested_count=2,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "root_cause_enrichment_enabled": True,
            }
        }
    )
    paused = service.run(request)
    assert paused.status == OrchestrationRunStatus.REVIEW_REQUIRED
    completed = service.run(request, resume=HumanResumeDecision(action="approve"))
    audit_session = service._control
    first_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    service.close()
    service2 = build_orchestration_service(
        session,
        gateway=gateway,
        knowledge_adapter=ki_adapter,
        memory_checkpointer=False,
        force_fake=True,
    )
    replay = service2.run(request, resume=HumanResumeDecision(action="approve"))
    assert replay.run_id == completed.run_id
    second_count = audit_session.scalar(
        select(func.count()).select_from(OrchestrationAuditEvent)
    )
    assert second_count == first_count
    service2.close()
