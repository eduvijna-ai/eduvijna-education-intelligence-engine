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
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models.orchestration import OrchestrationAuditEvent, OrchestrationIdempotencyRecord
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import build_orchestration_request, seed_day8_fixtures
from app.orchestration.scope_guard import verify_day8_scope_guard
from app.orchestration.service import OrchestrationService


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
    ki_adapter = FakeAnythingLLMAdapter()
    ctx = seed_day8_fixtures(session, adapter=ki_adapter)
    service = OrchestrationService(session, ki_adapter=ki_adapter, memory_checkpointer=True)
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
    tenant = service.run(
        build_orchestration_request(
            ctx,
            scenario="bad_provenance",
            idempotency_key="day8-tenant-key",
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

    replay = service.run(clean_request)
    idem_count = session.scalar(select(OrchestrationIdempotencyRecord.id).limit(10))
    audit_count = session.scalar(select(OrchestrationAuditEvent.id).limit(1))

    resume_engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(resume_engine)
    Base.metadata.create_all(resume_engine)
    with Session(resume_engine) as checkpoint_session:
        resume_adapter = FakeAnythingLLMAdapter()
        resume_ctx = seed_day8_fixtures(checkpoint_session, adapter=resume_adapter)
        checkpoint_service = OrchestrationService(
            checkpoint_session, ki_adapter=resume_adapter, memory_checkpointer=True
        )
        resume_request = build_orchestration_request(
            resume_ctx,
            scenario="repair_then_pass",
            idempotency_key="day8-resume-key",
            max_repairs=0,
        )
        config = {"configurable": {"thread_id": resume_request.run_id}}
        initial = {
            "run_id": resume_request.run_id,
            "thread_id": resume_request.run_id,
            "request": resume_request.model_dump(mode="json"),
            "request_hash": resume_request.request_hash(),
            "status": "planning",
            "prompt_versions": {},
            "repair_count_by_item": {},
            "repair_instructions_by_item": {},
            "warnings": [],
            "errors": [],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        checkpoint_service.compiled_graph.invoke(initial, config=config)
        paused = checkpoint_service.compiled_graph.get_state(config)
        resumed = checkpoint_service.compiled_graph.invoke(None, config=config)
        resume_ok = paused.next != () and resumed.get("final_result") is not None

    gateway_history = service.dependencies.gateway.call_history()
    no_provider_path = scope_guard["ok"]

    checks = {
        "graph_compiles": graph is not None,
        "day7_provenance_in_graph": bool(clean.source_revision_ids),
        "clean_pass_approved": clean.status == OrchestrationRunStatus.COMPLETED
        and clean.approved_count == 1,
        "repair_then_pass": repaired.status == OrchestrationRunStatus.COMPLETED,
        "blocking_not_approved": blocking.status != OrchestrationRunStatus.COMPLETED,
        "tenant_isolation": tenant.status != OrchestrationRunStatus.COMPLETED
        or tenant.approved_count == 0,
        "repair_exhaustion": exhausted.status
        in {OrchestrationRunStatus.REVIEW_REQUIRED, OrchestrationRunStatus.FAILED},
        "checkpoint_resume": resume_ok,
        "idempotent_replay": replay.run_id == clean.run_id
        and session.scalar(
            select(OrchestrationIdempotencyRecord).where(
                OrchestrationIdempotencyRecord.idempotency_key == clean_request.idempotency_key
            )
        )
        is not None,
        "audit_events_recorded": audit_count is not None,
        "gateway_calls_recorded": len(gateway_history) > 0,
        "no_direct_provider_path": no_provider_path,
        "candidate_sha": _resolve_candidate_sha(),
    }
    checks["ok"] = all(value for key, value in checks.items() if key != "candidate_sha")
    return {
        "checks": checks,
        "scope_guard": scope_guard,
        "clean_run_id": clean.run_id,
        "gateway_call_count": len(gateway_history),
        "idempotency_rows": idem_count,
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
        print(f"candidate_sha={checks['candidate_sha']}")
        for key, value in checks.items():
            if key == "candidate_sha":
                continue
            print(f"{key}={'PASS' if value else 'FAIL'}")
    checks_payload = report["checks"]
    if not isinstance(checks_payload, dict) or not bool(checks_payload.get("ok")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
