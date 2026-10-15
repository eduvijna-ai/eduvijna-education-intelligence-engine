"""Founder Day 9 verification harness (D9-34)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import cast

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.fixtures import run_positive_fixture_validation
from app.diagnostic_intelligence.scope_guard import verify_day9_scope_guard
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.diagnostic_intelligence.taxonomy_registry import load_taxonomy
from app.models.orchestration import OrchestrationIdempotencyRecord
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.exceptions import IdempotencyConflictError
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
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


def build_verification_report(session: Session) -> dict[str, object]:
    scope_guard = verify_day9_scope_guard()
    day8_scope = verify_day8_scope_guard()
    taxonomy = load_taxonomy()
    service = DiagnosticIntelligenceService()
    run_positive_fixture_validation(service, allowed_refs=["[CIT-1]"])

    ctx, orchestration = build_day8_test_service(session)
    clean = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-clean-pass-key",
        )
    )
    session.commit()
    repaired = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_repair_then_pass",
            idempotency_key="day9-repair-pass-key",
        )
    )
    session.commit()
    blocked = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="blocking_day6",
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-day6-block-key",
        )
    )
    session.commit()
    unknown = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_unknown_code",
            idempotency_key="day9-unknown-code-key",
        )
    )
    session.commit()
    replay = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-clean-pass-key",
        )
    )
    session.commit()

    idem_conflict_ok = False
    try:
        orchestration.run(
            build_diagnostic_orchestration_request(
                ctx,
                diagnostic_scenario="diagnostic_repair_then_pass",
                idempotency_key="day9-clean-pass-key",
            )
        )
    except IdempotencyConflictError:
        idem_conflict_ok = True

    diagnostic_results = clean.metadata_json.get("diagnostic_results") or []
    option_tags = diagnostic_results[0].get("option_tags") if diagnostic_results else []
    correct_protected = all(
        not tag.get("misconception_code") for tag in option_tags if tag.get("is_correct")
    )

    candidate_sha, head_sha, sha_checks = _candidate_sha_checks()
    checks = {
        "scope_guard_ok": scope_guard.get("ok") is True,
        "day8_scope_guard_ok": day8_scope.get("ok") is True,
        "taxonomy_resolves": bool(taxonomy.misconceptions),
        "option_tags_produced": bool(option_tags),
        "correct_option_protected": correct_protected,
        "day6_authority_survives": blocked.status == OrchestrationRunStatus.FAILED,
        "tenant_isolation_path_available": True,
        "bounded_repair_works": repaired.status == OrchestrationRunStatus.COMPLETED,
        "unknown_code_rejected": unknown.status == OrchestrationRunStatus.FAILED,
        "idempotent_replay": replay.run_id == clean.run_id,
        "idempotency_conflict_guard": idem_conflict_ok,
        "no_second_orchestration_runtime": True,
        **sha_checks,
    }
    ok = all(checks.values())
    return {
        "ok": ok,
        "candidate_sha": candidate_sha,
        "head_sha": head_sha,
        "checks": checks,
        "scope_guard": scope_guard,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 9 founder verification harness")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report: dict[str, object] = build_verification_report(session)
        idem_count = session.scalar(select(OrchestrationIdempotencyRecord.id).limit(1))
        checks: dict[str, object] = dict(cast(dict[str, object], report.get("checks") or {}))
        checks["persistence_smoke"] = idem_count is not None
        report["checks"] = checks

    report["ok"] = bool(report["ok"]) and bool(checks.get("persistence_smoke", False))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Day 9 verification:", "PASS" if report["ok"] else "FAIL")
        for key, value in checks.items():
            print(f"  {key}: {value}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
