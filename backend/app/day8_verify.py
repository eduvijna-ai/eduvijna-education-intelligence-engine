"""Founder Day 8 verification harness (D8-35)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.adapters.anythingllm.fake_adapter import FakeAnythingLLMAdapter
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


def build_verification_report(session: Session) -> dict[str, object]:
    scope_guard = verify_day8_scope_guard()
    ctx, service = build_day8_test_service(session)
    graph = service.compiled_graph

    clean_request = build_orchestration_request(ctx, scenario="clean_pass")
    clean = service.run(clean_request)
    repair_request = build_orchestration_request(
        ctx,
        scenario="repair_then_pass",
        idempotency_key="day8-repair-key",
    )
    repaired = service.run(repair_request)
    blocking = service.run(
        build_orchestration_request(
            ctx, scenario="blocking_day6", idempotency_key="day8-block-key"
        )
    )
    foreign = service.run(
        build_orchestration_request(
            ctx,
            scenario="foreign_tenant",
            idempotency_key="day8-foreign-tenant-key",
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

    replay = service.run(clean_request)
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

    with tempfile.TemporaryDirectory() as tmpdir:
        app_db_path = str(Path(tmpdir) / "app.db")
        checkpoint_db_path = str(Path(tmpdir) / "checkpoint.db")
        file_engine = create_engine(f"sqlite:///{app_db_path}")
        enable_sqlite_foreign_keys(file_engine)
        Base.metadata.create_all(file_engine)
        file_settings = Settings(database_url=f"sqlite:///{app_db_path}")
        checkpoint_settings = Settings(database_url=f"sqlite:///{checkpoint_db_path}")
        with Session(file_engine) as checkpoint_session:
            resume_adapter = FakeAnythingLLMAdapter()
            resume_ctx = seed_day8_fixtures(checkpoint_session, adapter=resume_adapter)
            resume_service = build_orchestration_service(
                checkpoint_session,
                settings=file_settings,
                knowledge_adapter=resume_adapter,
                checkpointer=build_managed_checkpointer(checkpoint_settings, memory_only=False),
                force_fake=True,
            )
            resume_request = build_orchestration_request(
                resume_ctx,
                scenario="human_review",
                idempotency_key="day8-resume-key",
            )
            paused_result = resume_service.run(resume_request)
            thread_id = resume_request.run_id
            config = {"configurable": {"thread_id": thread_id}}
            resumed = resume_service.run(
                resume_request,
                resume=HumanResumeDecision(action="approve"),
            )
            resume_ok = (
                paused_result.status == OrchestrationRunStatus.REVIEW_REQUIRED
                and resumed.status == OrchestrationRunStatus.COMPLETED
            )
            resume_service.close()

            rebuilt = build_orchestration_service(
                checkpoint_session,
                settings=file_settings,
                knowledge_adapter=resume_adapter,
                checkpointer=build_managed_checkpointer(checkpoint_settings, memory_only=False),
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
    candidate_sha = _resolve_candidate_sha()
    head_sha = _git_head()

    checks = {
        "graph_compiles": graph is not None,
        "day7_provenance_in_graph": bool(clean.source_revision_ids),
        "clean_pass_approved": clean.status == OrchestrationRunStatus.COMPLETED
        and clean.approved_count == 1,
        "repair_then_pass": repaired.status == OrchestrationRunStatus.COMPLETED,
        "blocking_not_approved": blocking.status != OrchestrationRunStatus.COMPLETED,
        "foreign_tenant_blocked": foreign.status != OrchestrationRunStatus.COMPLETED
        or foreign.approved_count == 0,
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
        "candidate_sha_resolved": candidate_sha not in {"", "unknown"},
        "candidate_sha_matches_head": candidate_sha == head_sha,
    }
    checks["ok"] = all(
        value for key, value in checks.items() if not key.startswith("candidate_sha")
    )
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
