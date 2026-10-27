from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from test_day10_r8_trust import (
    INST_A,
    _day9_audit,
    _load_snapshot,
    _root_cause_request,
    _seed_production_institution_graph,
    _session,
)
from test_day10_r11_trust import _approve_revision_mapping_binding

import app.models  # noqa: F401
from app.common.trust_execution import TrustExecutionMode
from app.db.base import Base
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
from app.models.education_intelligence import PolicyRegistryEntry
from app.models.orchestration import OrchestrationAuditEvent
from app.models.source import SourceRevision
from app.orchestration.contracts import OrchestrationRequest
from app.orchestration.nodes.root_cause import root_cause_enrich_node
from app.orchestration.state import OrchestrationGraphState
from app.root_cause_intelligence.enums import RootCauseIssueCode, RootCauseVerdictStatus
from app.root_cause_intelligence.mapping_authority import (
    ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
    ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
    mapping_evidence_checksum,
)
from app.root_cause_intelligence.service import RootCauseIntelligenceService
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext
from tests.migration_test_support import read_alembic_version, repository_alembic_head


def _run_alembic(database_path: Path, *args: str) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{database_path}"
    subprocess.run(
        ["alembic", "-c", str(backend_root / "alembic.ini"), *args],
        cwd=backend_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_day10_sqlite_alembic_upgrade_head(tmp_path: Path) -> None:
    database_path = tmp_path / "day10-migrate.db"
    _run_alembic(database_path, "upgrade", "head")
    assert read_alembic_version(database_path) == repository_alembic_head()


def test_day10_postgresql_ddl_compiles() -> None:
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        CreateTable(table).compile(dialect=dialect)


def test_day9_missing_organization_scope_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    mapping_overlay = _approve_revision_mapping_binding(session, ctx["source_revision_id"])
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000020"
    session.add(
        OrchestrationAuditEvent(
            id=audit_id,
            run_id="run-r14-org",
            request_hash="hash-r14-org",
            node_name="diagnostic_item",
            status="pass",
            attempt=1,
            source_revision_ids_json={"ids": [ctx["source_revision_id"]]},
            payload_json={
                "item_id": "item-r8",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "scope": {"institution_id": ctx["institution_id"]},
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
    session.commit()
    snapshot = _load_snapshot(session, ctx)
    trusted = RootCauseTrustedValidationContext.from_day9_accepted(
        item_id="item-r8",
        option_key="A",
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        day9_audit_ref=audit_id,
    )
    request = _root_cause_request(ctx, snapshot, institution_id=INST_A).model_copy(
        update={
            "orchestration_run_id": "run-r14-org",
            "orchestration_request_hash": "hash-r14-org",
        }
    )
    result = RootCauseIntelligenceService().analyze(
        request,
        trusted=trusted,
        execution_mode=TrustExecutionMode.PRODUCTION,
        control_session=session,
    )
    assert RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in result.issue_codes
    assert result.hypotheses == []


def test_self_attested_binding_without_revision_approval_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    revision = session.get(SourceRevision, ctx["source_revision_id"])
    assert revision is not None
    content_checksum = "b" * 64
    forged_checksum = mapping_evidence_checksum(
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        candidate_concept_codes=["whole-number-addition", "multi-step-addition"],
        source_locator="forged/locator",
        mapping_registry_version="root-cause-mapping@v1",
        source_revision_id=ctx["source_revision_id"],
        source_content_checksum=content_checksum,
    )
    revision.metadata_json = {
        "root_cause_mapping_bindings": [
            {
                "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                "candidate_concept_codes": ["whole-number-addition", "multi-step-addition"],
                "source_locator": "forged/locator",
                "mapping_registry_version": "root-cause-mapping@v1",
                "source_revision_id": ctx["source_revision_id"],
                "source_content_checksum": content_checksum,
                "mapping_evidence_checksum": forged_checksum,
                "approval_status": "active",
                "approval_fingerprint": "self-forged",
                "approved_by": "forger",
            }
        ]
    }
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={
                "overlays": [
                    {
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "mapping_registry_version": "root-cause-mapping@v1",
                        "candidate_concept_codes": [
                            "whole-number-addition",
                            "multi-step-addition",
                        ],
                        "source_revision_ids": [ctx["source_revision_id"]],
                        "source_locator": "forged/locator",
                        "mapping_evidence_checksum": forged_checksum,
                    }
                ]
            },
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000021"
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


def test_root_cause_enrich_rejects_mismatched_day9_lineage(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = _seed_production_institution_graph(session)
    mapping_overlay = _approve_revision_mapping_binding(session, ctx["source_revision_id"])
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            version=ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            status="active",
            payload_json={"overlays": [mapping_overlay]},
        )
    )
    audit_id = "00000000-0000-4000-8000-000000000022"
    _day9_audit(session, ctx, audit_id=audit_id, run_id="run-r8", request_hash="hash-r8")
    session.commit()
    deps = MagicMock()
    deps.session = session
    deps.control_session = session
    request = OrchestrationRequest(
        idempotency_key="r14-rc-mismatch",
        retrieval_profile_version="default@v1",
        metadata_json={"root_cause_enrichment_enabled": True},
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
    )
    state: OrchestrationGraphState = {
        "run_id": "run-mismatch",
        "request_hash": "hash-mismatch",
        "request": request.model_dump(mode="json"),
        "root_cause_results": [],
        "diagnostic_validation": [{"item_id": "item-r8", "blocking": False}],
        "diagnostic_results": [
            {
                "item_id": "item-r8",
                "taxonomy_version": DEFAULT_TAXONOMY_VERSION,
                "audit_refs": [audit_id],
                "option_tags": [
                    {
                        "option_key": "A",
                        "is_correct": False,
                        "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                        "validation_status": DiagnosticValidationStatus.PASS.value,
                        "evidence_refs": ["cite-r14"],
                    }
                ],
            }
        ],
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
                "item_id": "item-r8",
                "concept_codes": ["multi-step-addition"],
                "source_revision_ids": [ctx["source_revision_id"]],
            }
        ],
        "deterministic_validation": [{"item_id": "item-r8", "blocking": False}],
        "knowledge_context": KnowledgeContextPack(
            query_id="r14-mismatch",
            query_text="addition",
            retrieval_profile_version="ki-retrieval-v1",
            evidence=[],
            citations=[],
            scope=AppliedKnowledgeScope(curriculum_version_id=ctx["curriculum_version_id"]),
            warnings=[],
            bounded_text="",
        ).model_dump(mode="json"),
    }
    update = root_cause_enrich_node(state, deps)
    results = update.get("root_cause_results") or []
    assert len(results) == 1
    assert results[0].get("hypotheses") == []
    assert results[0].get("verdict_status") in {
        RootCauseVerdictStatus.REVIEW_REQUIRED.value,
        RootCauseVerdictStatus.FAIL.value,
        RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE.value,
    }
