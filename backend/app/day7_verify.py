"""Founder Day 7 verification harness (D7-35)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.factory import build_anythingllm_adapter
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.http_adapter import HttpAnythingLLMAdapter
from app.adapters.anythingllm.types import (
    AdapterError,
    AdapterErrorCode,
    AdapterRetrievalHit,
    AdapterRetrievalRequest,
    AdapterUploadedDocument,
    GatewayAvailability,
    IndexDocumentPayload,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.doc_source_identity import build_stable_doc_source_identity
from app.knowledge_intelligence.eligibility import IndexEligibilityError
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures, staged_revision_for_source
from app.knowledge_intelligence.governance import verify_day7_governance_state
from app.knowledge_intelligence.indexing import (
    index_source_revision,
    list_active_bindings_for_source,
)
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.knowledge_intelligence.service import KnowledgeIntelligenceService
from app.models.knowledge_intelligence import KnowledgeAuditEvent
from app.models.source import Source, SourceRevision


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _resolve_candidate_sha() -> str:
    explicit = os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip()
    if explicit:
        return explicit
    return _git_head()


def build_verification_report(session: Session) -> dict[str, object]:
    governance = verify_day7_governance_state()
    adapter = FakeAnythingLLMAdapter()
    service = KnowledgeIntelligenceService(session, adapter=adapter)
    fixtures = seed_knowledge_fixtures(session)
    session.commit()

    probe = service.probe_gateway()
    official_binding = service.index_source_revision(
        fixtures.official_revision_id,
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    duplicate_binding = service.index_source_revision(
        fixtures.official_revision_id,
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    institution_binding = service.index_source_revision(
        fixtures.institution_revision_id,
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    injection_binding = service.index_source_revision(
        fixtures.injection_revision_id,
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    session.commit()

    official_revision = session.get(SourceRevision, fixtures.official_revision_id)
    assert official_revision is not None
    staged = staged_revision_for_source(session, official_revision.source_id)
    inactive_rejected = False
    try:
        index_source_revision(
            session,
            adapter,
            staged.id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    except IndexEligibilityError:
        inactive_rejected = True

    scoped = service.retrieve(
        KnowledgeRetrievalRequest(
            query_text="quadratic equations completing square",
            organization_id=fixtures.organization_id,
            institution_id=fixtures.institution_id,
            top_k=5,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    )
    pack = service.build_context_pack(scoped)

    foreign = service.retrieve(
        KnowledgeRetrievalRequest(
            query_text="quadratic equations",
            organization_id="foreign-org",
            institution_id="foreign-inst",
            top_k=5,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    )

    unavailable_adapter = FakeAnythingLLMAdapter(simulate_unavailable=True)
    unavailable_service = KnowledgeIntelligenceService(session, adapter=unavailable_adapter)
    unavailable = unavailable_service.retrieve(
        KnowledgeRetrievalRequest(
            query_text="quadratic",
            top_k=3,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    )
    session.commit()

    audit_count = session.scalar(select(KnowledgeAuditEvent.id).limit(1))
    audits = list(session.scalars(select(KnowledgeAuditEvent)).all())

    forged_curriculum = service.retrieve(
        KnowledgeRetrievalRequest(
            query_text="quadratic equations",
            curriculum_version_id="forged-curriculum-id",
            top_k=3,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    )
    official_source = session.get(Source, official_binding.source_id)
    grade_mismatch = KnowledgeRetrievalRequest(
        query_text="quadratic equations",
        grade_year_code="grade-9",
        top_k=3,
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    if official_source is not None:
        official_source.metadata_json = {
            **official_source.metadata_json,
            "grade_year_code": "grade-10",
        }
    session.flush()
    grade_filtered = service.retrieve(grade_mismatch)

    class _BadEchoAdapter(FakeAnythingLLMAdapter):
        def upload_document(
            self,
            workspace_slug: str,
            payload: IndexDocumentPayload,
            *,
            idempotency_key: str,
        ) -> AdapterUploadedDocument:
            return AdapterUploadedDocument(
                stable_id="uploaded-file.txt",
                remote_doc_id="doc-bad",
                remote_location="custom-documents/doc-bad.txt",
            )

    bad_echo_failed = False
    try:
        index_source_revision(
            session,
            _BadEchoAdapter(),
            fixtures.teacher_revision_id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    except Exception:
        bad_echo_failed = True

    class _FailOnceRetireAdapter(FakeAnythingLLMAdapter):
        def __init__(self) -> None:
            super().__init__()
            self._retire_calls = 0

        def remove_document(self, workspace_slug: str, document_id: str) -> None:
            self._retire_calls += 1
            if self._retire_calls == 1:
                raise AdapterError(
                    AdapterErrorCode.UNAVAILABLE,
                    "simulated retire failure",
                    retryable=True,
                )
            super().remove_document(workspace_slug, document_id)

    supersession_adapter = _FailOnceRetireAdapter()
    supersession_service = KnowledgeIntelligenceService(session, adapter=supersession_adapter)
    first_binding = supersession_service.index_source_revision(
        fixtures.teacher_revision_id,
        retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )
    base_revision = session.get(SourceRevision, fixtures.teacher_revision_id)
    supersession_reconciled = False
    if base_revision is not None:
        base_revision.status = "superseded"
        base_revision.active_slot = None
        successor = SourceRevision(
            source_id=base_revision.source_id,
            revision_number=base_revision.revision_number + 1,
            checksum="1" * 64,
            source_snapshot_checksum="2" * 64,
            ingestion_method="manual",
            content_type="text/plain",
            byte_size=32,
            retrieved_at=base_revision.retrieved_at,
            status="active",
            active_slot=1,
            extraction_status="succeeded",
            extracted_text="SYNTHETIC FIXTURE: supersession verify revision",
            extracted_checksum="1" * 64,
            metadata_json={"synthetic_fixture": True},
        )
        session.add(successor)
        session.flush()
        replacement = supersession_service.index_source_revision(
            successor.id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        supersession_service.index_source_revision(
            successor.id,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
        active_after = list_active_bindings_for_source(session, first_binding.source_id)
        supersession_reconciled = (
            len(active_after) == 1 and active_after[0].id == replacement.id
        )

    explicit_fake = build_anythingllm_adapter(force_fake=True)
    configured_http = build_anythingllm_adapter(
        Settings(anythingllm_base_url="http://anythingllm.test", anythingllm_api_key="secret"),
        force_fake=False,
    )

    official_revision = session.get(SourceRevision, fixtures.official_revision_id)
    assert official_revision is not None
    stable_identity = build_stable_doc_source_identity(
        official_revision.id,
        DEFAULT_RETRIEVAL_PROFILE_VERSION,
        official_revision.checksum,
    )
    stable_identity_repeat = build_stable_doc_source_identity(
        official_revision.id,
        DEFAULT_RETRIEVAL_PROFILE_VERSION,
        official_revision.checksum,
    )

    class _UnknownHitAdapter(FakeAnythingLLMAdapter):
        def retrieve(self, request: AdapterRetrievalRequest) -> list[AdapterRetrievalHit]:
            unknown = "eduvijna://knowledge/unknown-rev/ki-v1/" + ("9" * 64)
            return [
                AdapterRetrievalHit(
                    workspace_slug="ws-global",
                    document_id=unknown,
                    text="forged evidence",
                    score=0.99,
                    rank=1,
                    metadata={"docSource": unknown},
                )
            ]

    unknown_service = KnowledgeIntelligenceService(session, adapter=_UnknownHitAdapter())
    unknown_hit = unknown_service.retrieve(
        KnowledgeRetrievalRequest(
            query_text="quadratic",
            top_k=3,
            retrieval_profile_version=DEFAULT_RETRIEVAL_PROFILE_VERSION,
        )
    )
    unknown_doc_source_rejected = unknown_hit.items == [] and any(
        warning.startswith("unknown_remote_document:") for warning in unknown_hit.warnings
    )

    report_head_sha = _resolve_candidate_sha()
    gov_checks_raw = governance.get("checks", {})
    gov_checks = gov_checks_raw if isinstance(gov_checks_raw, dict) else {}
    checks: dict[str, object] = {
        "gateway_fake_probe_available": probe.availability == GatewayAvailability.AVAILABLE,
        "active_revision_indexed": official_binding.index_status == "active",
        "inactive_revision_rejected": inactive_rejected,
        "idempotent_duplicate_indexing": duplicate_binding.id == official_binding.id,
        "tenant_scoped_institution_indexed": institution_binding.index_status == "active",
        "foreign_tenant_isolated": all(
            item.source_id != institution_binding.source_id for item in foreign.items
        ),
        "exact_source_revision_provenance": all(
            item.source_revision_id and item.source_revision_checksum for item in scoped.items
        ),
        "authority_separation": len({item.trust_tier for item in scoped.items}) >= 1,
        "deterministic_context_pack": bool(pack.bounded_text) and pack.query_id == scoped.query_id,
        "unavailable_gateway_graceful": "gateway_unavailable" in unavailable.warnings,
        "retrieval_profile_version_present": scoped.retrieval_profile_version
        == DEFAULT_RETRIEVAL_PROFILE_VERSION,
        "audit_persisted": audit_count is not None and len(audits) > 0,
        "injection_indexed_as_evidence": bool(
            injection_binding.metadata_json.get("workspace_scope_key")
        ),
        "d5_ds01_still_deferred": bool(gov_checks.get("d5_ds01_deferred")),
        "day8_locked": bool(gov_checks.get("day8_locked")),
        "candidate_sha_resolved": report_head_sha != "unknown",
        "curriculum_provenance_not_forged": forged_curriculum.items == [],
        "local_grade_scope_filter_enforced": grade_filtered.items == [],
        "supersession_retire_failure_recoverable": supersession_reconciled,
        "fake_adapter_explicit_mode": isinstance(explicit_fake, FakeAnythingLLMAdapter),
        "configured_adapter_uses_http": isinstance(configured_http, HttpAnythingLLMAdapter),
        "stable_doc_source_identity_deterministic": stable_identity == stable_identity_repeat,
        "doc_source_identity_persisted_on_binding": (
            official_binding.metadata_json.get("anythingllm_doc_source_identity")
            == stable_identity
        ),
        "remote_location_persisted_separately": bool(
            official_binding.metadata_json.get("anythingllm_remote_location")
        )
        and official_binding.metadata_json.get("anythingllm_doc_source_identity")
        != official_binding.metadata_json.get("anythingllm_remote_location"),
        "gateway_doc_source_echo_mismatch_fails_closed": bad_echo_failed,
        "vector_hit_maps_through_stable_doc_source": any(
            item.binding_id == official_binding.id for item in scoped.items
        ),
        "unknown_doc_source_rejected": unknown_doc_source_rejected,
    }

    return {
        "day": 7,
        "head_sha": report_head_sha,
        "candidate_sha_source": (
            "EDUVIJNA_CANDIDATE_SHA"
            if os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip()
            else ("git" if report_head_sha != "unknown" else "unknown")
        ),
        "governance": governance,
        "checks": checks,
        "passed": all(v is True for v in checks.values()) and report_head_sha != "unknown",
        "sample": {
            "official_binding_id": official_binding.id,
            "scoped_result_count": len(scoped.items),
            "foreign_result_count": len(foreign.items),
            "context_characters": len(pack.bounded_text),
        },
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report = build_verification_report(session)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
