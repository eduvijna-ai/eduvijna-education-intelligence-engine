from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.knowledge_intelligence.contracts import KnowledgeContextPack, KnowledgeEvidenceItem
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.root_cause_trust import (
    build_trusted_validation_from_state,
    option_allowed_source_revision_ids,
)
from app.prerequisite_intelligence.fixtures import (
    load_day10_fixture_snapshot,
    seed_day10_prerequisite_fixture,
)
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-rc-orch.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _evidence(revision_id: str, citation: str) -> KnowledgeEvidenceItem:
    return KnowledgeEvidenceItem(
        source_id="src",
        source_revision_id=revision_id,
        source_revision_checksum="a" * 64,
        binding_id="bind",
        trust_tier="official",
        authority_label="fixture",
        title="t",
        locator="loc",
        snippet="snippet",
        retrieval_score=1.0,
        retrieval_rank=1,
        anythingllm_workspace="ws",
        anythingllm_document_id="doc",
        citation_label=citation,
    )


def test_option_source_requires_matching_citation() -> None:
    context = KnowledgeContextPack.model_construct(
        evidence=[_evidence("rev-a", "cite-a"), _evidence("rev-b", "cite-b")]
    )
    draft = {"item_id": "item-a", "source_revision_ids": ["rev-a", "rev-b"]}
    tag_a = {"evidence_refs": ["cite-a"]}
    tag_b = {"evidence_refs": ["cite-b"]}
    assert option_allowed_source_revision_ids(draft, context, tag_a) == ["rev-a"]
    assert option_allowed_source_revision_ids(draft, context, tag_b) == ["rev-b"]


def test_trusted_validation_requires_item_audit_ref() -> None:
    trusted = build_trusted_validation_from_state(
        item_id="item-1",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        diagnostic_validation=[{"item_id": "item-1", "blocking": False}],
        diagnostic_results=[
            {
                "item_id": "item-1",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "audit_refs": ["audit-item-1"],
                "option_tags": [
                    {
                        "option_key": "A",
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                    }
                ],
            }
        ],
    )
    assert trusted is not None
    assert trusted.day9_audit_ref == "audit-item-1"

    missing_audit = build_trusted_validation_from_state(
        item_id="item-1",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        diagnostic_validation=[{"item_id": "item-1", "blocking": False}],
        diagnostic_results=[
            {
                "item_id": "item-1",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "option_tags": [
                    {
                        "option_key": "A",
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                    }
                ],
            }
        ],
    )
    assert missing_audit is None


def test_forged_day9_audit_rejected_in_production(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    service = RootCauseIntelligenceService()
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-1",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref="forged-audit-id",
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
    assert result.hypotheses == []


def test_persisted_day9_audit_allows_production_pass(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    audit_id = "00000000-0000-4000-8000-000000000001"
    session.add(
        OrchestrationAuditEvent(
            id=audit_id,
            run_id="run-test",
            request_hash="hash",
            node_name="diagnostic_item",
            status="pass",
            attempt=1,
            payload_json={
                "diagnostic": True,
                "item_id": "item-1",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "option_traces": [
                    {
                        "option_key": "A",
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                    }
                ],
            },
        )
    )
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
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
            ),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        ),
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION not in result.issue_codes
    assert len(result.hypotheses) >= 1
