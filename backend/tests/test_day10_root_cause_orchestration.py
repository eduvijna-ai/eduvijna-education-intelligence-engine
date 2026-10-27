from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.knowledge_intelligence.contracts import KnowledgeContextPack, KnowledgeEvidenceItem
from app.orchestration.root_cause_trust import (
    build_trusted_validation_from_state,
    item_allowed_source_revision_ids,
)
from app.prerequisite_intelligence.fixtures import (
    load_day10_fixture_snapshot,
    seed_day10_prerequisite_fixture,
)
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-rc-orch.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _evidence(revision_id: str) -> KnowledgeEvidenceItem:
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
        citation_label="cite",
    )


def test_per_item_source_intersection_blocks_cross_item_revision() -> None:
    context = KnowledgeContextPack.model_construct(
        evidence=[_evidence("rev-a"), _evidence("rev-b")]
    )
    draft_a = {"item_id": "item-a", "source_revision_ids": ["rev-a"]}
    draft_b = {"item_id": "item-b", "source_revision_ids": ["rev-b"]}
    assert item_allowed_source_revision_ids(draft_a, context) == ["rev-a"]
    assert item_allowed_source_revision_ids(draft_b, context) == ["rev-b"]


def test_trusted_validation_requires_diagnostic_validation_pass(tmp_path: Path) -> None:
    trusted = build_trusted_validation_from_state(
        item_id="item-1",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        diagnostic_validation=[
            {"item_id": "item-1", "blocking": False},
        ],
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
        diagnostic_audit_refs=["audit-day9-1"],
    )
    assert trusted is not None
    assert trusted.trust_source == "day9_accepted_verdict"
    assert trusted.day9_audit_ref == "audit-day9-1"

    blocked = build_trusted_validation_from_state(
        item_id="item-1",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        diagnostic_validation=[{"item_id": "item-1", "blocking": True}],
        diagnostic_results=[],
        diagnostic_audit_refs=[],
    )
    assert blocked is None


def test_day9_trusted_context_allows_positive_root_cause(tmp_path: Path) -> None:
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
        day9_audit_ref="persisted-audit",
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
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION not in result.issue_codes
    assert len(result.hypotheses) >= 1
