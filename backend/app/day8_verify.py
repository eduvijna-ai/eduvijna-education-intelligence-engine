"""Founder Day 8 verification harness (D8-35)."""

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
from app.adapters.anythingllm.types import (
    AdapterRetrievalHit,
    AdapterRetrievalRequest,
    AdapterRetrievalResponse,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models.orchestration import OrchestrationAuditEvent, OrchestrationIdempotencyRecord
from app.orchestration.checkpoint import build_managed_checkpointer
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.exceptions import IdempotencyConflictError, OrchestrationConfigurationError
from app.orchestration.factory import build_orchestration_service
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_orchestration_request,
    seed_day8_fixtures,
)
from app.orchestration.gateway.factory import build_generation_gateway
from app.orchestration.human_decision import HumanResumeDecision
from app.orchestration.scope_guard import verify_day8_scope_guard


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


def _candidate_sha_checks() -> tuple[str, str, dict[str, bool]]:
    candidate_sha = _resolve_candidate_sha()
    head_sha = _git_head()
    return (
        candidate_sha,
        head_sha,
        {
            "candidate_sha_resolved": candidate_sha not in {"", "unknown"},
            "candidate_sha_matches_head": candidate_sha == head_sha,
        },
    )


class _ForeignInjectingAdapter:
    """Wrap the Day-7 fake and simulate a remote cross-tenant hit."""

    def __init__(
        self,
        delegate: FakeAnythingLLMAdapter,
        *,
        injected: list[tuple[str, str]],
    ) -> None:
        self._delegate = delegate
        self._injected = injected

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def retrieve(self, request: AdapterRetrievalRequest) -> AdapterRetrievalResponse:
        response = self._delegate.retrieve(request)
        if not request.workspace_slugs:
            return response
        workspace = request.workspace_slugs[0]
        hits = list(response.hits)
        for index, (doc_source, text) in enumerate(
            self._injected, start=len(hits) + 1
        ):
            hits.append(
                AdapterRetrievalHit(
                    workspace_slug=workspace,
                    document_id=doc_source,
                    text=text,
                    score=1.0,
                    rank=index,
                    metadata={
                        "docSource": doc_source,
                        "synthetic_foreign_injection": True,
                    },
                )
            )
        return AdapterRetrievalResponse(
            hits=tuple(hits),
            warnings=response.warnings,
        )


def build_verification_report(session: Session) -> dict[str, object]:
    scope_guard = verify_day8_scope_guard()
    ctx, service = build_day8_test_service(session)
    graph = service.compiled_graph

    clean_request = build_orchestration_request(ctx, scenario="clean_pass")
    clean = service.run(clean_request)
    session.commit()
    repair_request = build_orchestration_request(
        ctx,
        scenario="repair_then_pass",
        idempotency_key="day8-repair-key",
    )
    repaired = service.run(repair_request)
    session.commit()
    blocking = service.run(
        build_orchestration_request(
            ctx, scenario="blocking_day6", idempotency_key="day8-block-key"
        )
    )
    session.commit()
    from app.knowledge_intelligence.contracts import KnowledgeContextPack
    from app.knowledge_intelligence.fixtures import _OFFICIAL_TEXT, _active_revision
    from app.knowledge_intelligence.indexing import index_source_revision
    from app.models import Institution, Organization, Teacher
    from app.models.enums import SourceStatus, SourceTrustTier, SourceType
    from app.models.source import Source

    org_b = Organization(code="ki-org-b", name="KI Org B")
    session.add(org_b)
    session.flush()
    inst_b = Institution(organization_id=org_b.id, code="ki-inst-b", name="KI Inst B")
    session.add(inst_b)
    session.flush()
    foreign_source = Source(
        organization_id=org_b.id,
        institution_id=inst_b.id,
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="Synthetic foreign organization source",
        trust_tier=SourceTrustTier.INSTITUTION.value,
        status=SourceStatus.ACTIVE.value,
        metadata_json={"synthetic_fixture": True, "fixture_role": "foreign_tenant"},
    )
    session.add(foreign_source)
    session.flush()
    foreign_revision = _active_revision(
        foreign_source.id,
        _OFFICIAL_TEXT + " ORG-B-MARKER",
        revision_number=1,
        checksum_suffix="fb",
    )
    session.add(foreign_revision)

    foreign_teacher = Teacher(
        institution_id=ctx["institution_id"],
        external_code="foreign-teacher",
        display_name="Synthetic Foreign Teacher",
    )
    session.add(foreign_teacher)
    session.flush()
    teacher_source = Source(
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
        teacher_id=foreign_teacher.id,
        source_type=SourceType.TEACHER_CONTENT.value,
        title="Synthetic foreign teacher source",
        trust_tier=SourceTrustTier.TEACHER.value,
        status=SourceStatus.ACTIVE.value,
        metadata_json={"synthetic_fixture": True, "fixture_role": "foreign_teacher"},
    )
    session.add(teacher_source)
    session.flush()
    teacher_revision = _active_revision(
        teacher_source.id,
        _OFFICIAL_TEXT + " TEACHER-B-MARKER",
        revision_number=1,
        checksum_suffix="ft",
    )
    session.add(teacher_revision)
    session.flush()

    ki_probe_adapter = service.dependencies.knowledge_service._adapter
    foreign_binding = index_source_revision(
        session,
        ki_probe_adapter,
        foreign_revision.id,
        retrieval_profile_version=clean_request.retrieval_profile_version,
    )
    teacher_binding = index_source_revision(
        session,
        ki_probe_adapter,
        teacher_revision.id,
        retrieval_profile_version=clean_request.retrieval_profile_version,
    )
    session.commit()

    foreign_doc_source = str(
        foreign_binding.metadata_json.get("anythingllm_doc_source_identity") or ""
    )
    teacher_doc_source = str(
        teacher_binding.metadata_json.get("anythingllm_doc_source_identity") or ""
    )
    service.dependencies.knowledge_service._adapter = _ForeignInjectingAdapter(
        ki_probe_adapter,
        injected=[
            (foreign_doc_source, _OFFICIAL_TEXT + " ORG-B-MARKER"),
            (teacher_doc_source, _OFFICIAL_TEXT + " TEACHER-B-MARKER"),
        ],
    )
    tenant_request = build_orchestration_request(
        ctx,
        idempotency_key="day8-tenant-isolation-key",
    )
    tenant_result = service.run(tenant_request)
    tenant_snapshot = service.compiled_graph.get_state(
        {"configurable": {"thread_id": tenant_result.run_id}}
    )
    tenant_context = KnowledgeContextPack.model_validate(
        tenant_snapshot.values.get("knowledge_context") or {}
    )
    service.dependencies.knowledge_service._adapter = ki_probe_adapter
    foreign_revision_ids = {foreign_revision.id, teacher_revision.id}
    context_revision_ids = {
        item.source_revision_id for item in tenant_context.evidence
    }
    drop_warnings = [
        warning
        for warning in tenant_context.warnings
        if warning.startswith("dropped_foreign_tenant:")
    ]
    foreign_tenant_scope_enforced = (
        tenant_result.status == OrchestrationRunStatus.COMPLETED
        and foreign_revision_ids.isdisjoint(context_revision_ids)
        and foreign_revision_ids.isdisjoint(set(tenant_result.source_revision_ids))
        and all(
            any(revision_id in warning for warning in drop_warnings)
            for revision_id in foreign_revision_ids
        )
    )
    exhausted = service.run(
        build_orchestration_request(
            ctx,
            scenario="repair_then_pass",
            idempotency_key="day8-exhaust-key",
            max_repairs=0,
        )
    )
    injection = service.run(
        build_orchestration_request(
            ctx, scenario="injection_evidence", idempotency_key="day8-injection-key"
        )
    )
    session.commit()

    replay = service.run(clean_request)
    session.commit()
    idem_count = session.scalar(select(OrchestrationIdempotencyRecord.id).limit(10))
    audit_count = session.scalar(select(OrchestrationAuditEvent.id).limit(1))

    idem_conflict_ok = False
    try:
        service.run(
            build_orchestration_request(
                ctx, scenario="repair_then_pass", idempotency_key=clean_request.idempotency_key
            )
        )
    except IdempotencyConflictError:
        idem_conflict_ok = True

    shared_checkpointer = build_managed_checkpointer(
        Settings(database_url="sqlite:///:memory:"), memory_only=True
    )
    resume_engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(resume_engine)
    Base.metadata.create_all(resume_engine)
    with Session(resume_engine) as checkpoint_session:
            resume_adapter = FakeAnythingLLMAdapter()
            resume_ctx = seed_day8_fixtures(checkpoint_session, adapter=resume_adapter)
            resume_service = build_orchestration_service(
                checkpoint_session,
                knowledge_adapter=resume_adapter,
                checkpointer=shared_checkpointer,
                force_fake=True,
            )
            resume_request = build_orchestration_request(
                resume_ctx,
                scenario="human_review",
                idempotency_key="day8-resume-key",
            )
            paused_result = resume_service.run(resume_request)
            checkpoint_session.commit()
            thread_id = paused_result.run_id
            config = {"configurable": {"thread_id": thread_id}}
            calls_before = len(resume_service.dependencies.gateway.call_history())
            assert calls_before > 0
            resume_service.close()

            resume_service_b = build_orchestration_service(
                checkpoint_session,
                knowledge_adapter=resume_adapter,
                checkpointer=shared_checkpointer,
                force_fake=True,
            )
            resumed = resume_service_b.run(
                resume_request,
                resume=HumanResumeDecision(action="approve"),
            )
            checkpoint_session.commit()
            calls_after = len(resume_service_b.dependencies.gateway.call_history())
            resume_ok = (
                paused_result.status == OrchestrationRunStatus.REVIEW_REQUIRED
                and resumed.status == OrchestrationRunStatus.COMPLETED
                and calls_after == 0
            )
            resume_service_b.close()

            rebuilt = build_orchestration_service(
                checkpoint_session,
                knowledge_adapter=resume_adapter,
                checkpointer=shared_checkpointer,
                force_fake=True,
            )
            try:
                state = rebuilt.compiled_graph.get_state(config)
                persistent_resume_ok = state.values.get("final_result") is not None
            finally:
                rebuilt.close()

    prod_config_missing = False
    try:
        build_generation_gateway(
            Settings(
                anythingllm_base_url="",
                anythingllm_api_key="",
                anythingllm_orchestration_workspace="",
            ),
            force_fake=False,
        )
    except OrchestrationConfigurationError:
        prod_config_missing = True

    gateway_history = service.dependencies.gateway.call_history()
    candidate_sha, head_sha, candidate_checks = _candidate_sha_checks()

    checks = {
        "graph_compiles": graph is not None,
        "day7_provenance_in_graph": bool(clean.source_revision_ids),
        "clean_pass_approved": clean.status == OrchestrationRunStatus.COMPLETED
        and clean.approved_count == 1,
        "repair_then_pass": repaired.status == OrchestrationRunStatus.COMPLETED,
        "blocking_not_approved": blocking.status != OrchestrationRunStatus.COMPLETED,
        "foreign_tenant_scope_enforced": foreign_tenant_scope_enforced,
        "repair_exhaustion": exhausted.status
        in {OrchestrationRunStatus.REVIEW_REQUIRED, OrchestrationRunStatus.FAILED},
        "prompt_injection_handled": injection.status != OrchestrationRunStatus.COMPLETED
        or injection.approved_count == 0,
        "checkpoint_resume_hitl": resume_ok,
        "persistent_checkpoint_state": persistent_resume_ok,
        "idempotent_replay": replay.run_id == clean.run_id
        and session.scalar(
            select(OrchestrationIdempotencyRecord).where(
                OrchestrationIdempotencyRecord.idempotency_key == clean_request.idempotency_key
            )
        )
        is not None,
        "idempotency_conflict": idem_conflict_ok,
        "audit_events_recorded": audit_count is not None,
        "audit_refs_on_result": bool(clean.audit_refs),
        "gateway_calls_recorded": len(gateway_history) > 0,
        "no_direct_provider_path": scope_guard["ok"],
        "production_gateway_fail_closed": prod_config_missing,
        **candidate_checks,
    }
    checks["ok"] = all(value for key, value in checks.items())
    return {
        "checks": checks,
        "scope_guard": scope_guard,
        "clean_run_id": clean.run_id,
        "gateway_call_count": len(gateway_history),
        "idempotency_rows": idem_count,
        "candidate_sha": candidate_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Day 8 Founder verification")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report = build_verification_report(session)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        checks_raw = report["checks"]
        if not isinstance(checks_raw, dict):
            raise SystemExit("invalid verification report")
        checks: dict[str, object] = checks_raw
        print(f"candidate_sha={report.get('candidate_sha', checks.get('candidate_sha'))}")
        for key, value in checks.items():
            if key.startswith("candidate_sha"):
                continue
            print(f"{key}={'PASS' if value else 'FAIL'}")
    checks_payload = report["checks"]
    if not isinstance(checks_payload, dict) or not bool(checks_payload.get("ok")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
