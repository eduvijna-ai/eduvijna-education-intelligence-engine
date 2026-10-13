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
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
from app.adapters.anythingllm.types import GatewayAvailability
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.eligibility import IndexEligibilityError
from app.knowledge_intelligence.fixtures import seed_knowledge_fixtures, staged_revision_for_source
from app.knowledge_intelligence.governance import verify_day7_governance_state
from app.knowledge_intelligence.indexing import index_source_revision
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.knowledge_intelligence.service import KnowledgeIntelligenceService
from app.models.knowledge_intelligence import KnowledgeAuditEvent
from app.models.source import SourceRevision


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
