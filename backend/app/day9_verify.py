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
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.checkpoint_proof import (
    prove_interrupted_diagnostic_checkpoint_restart,
)
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
)
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_tags,
    run_positive_fixture_validation,
)
from app.diagnostic_intelligence.scope_guard import verify_day9_scope_guard
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.diagnostic_intelligence.taxonomy_registry import load_taxonomy
from app.models.orchestration import OrchestrationAuditEvent, OrchestrationIdempotencyRecord
from app.orchestration.day9_tenant_fixtures import seed_day9_foreign_tenant_revisions
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


def _tenant_issue_codes(result: object) -> list[str]:
    issue_codes: list[str] = []
    metadata = getattr(result, "metadata_json", {}) or {}
    for entry in metadata.get("diagnostic_results") or []:
        for tag in entry.get("option_tags") or []:
            issue_codes.extend(list(tag.get("issue_codes") or []))
    return issue_codes


def _tenant_isolation_proof(
    orchestration: object, ctx: dict[str, str], session: Session
) -> tuple[bool, str]:
    foreign = seed_day9_foreign_tenant_revisions(session, ctx)
    cases = [
        (foreign.foreign_organization_revision_id, "day9-tenant-org-proof"),
        (foreign.foreign_institution_revision_id, "day9-tenant-inst-proof"),
        (foreign.foreign_teacher_revision_id, "day9-tenant-teacher-proof"),
    ]
    for revision_id, key in cases:
        result = orchestration.run(  # type: ignore[attr-defined]
            build_diagnostic_orchestration_request(
                ctx,
                diagnostic_scenario="diagnostic_foreign_revision",
                diagnostic_foreign_revision_id=revision_id,
                idempotency_key=key,
            )
        )
        if "tenant_evidence_mismatch" not in _tenant_issue_codes(result):
            return False, foreign.foreign_organization_revision_id
    return True, foreign.foreign_organization_revision_id


def _hitl_diagnostic_review_proof(orchestration: object, ctx: dict[str, str]) -> bool:
    from app.orchestration.fixtures import build_orchestration_request
    from app.orchestration.human_decision import HumanResumeDecision

    request = build_orchestration_request(
        ctx,
        scenario="non_arithmetic_diagnostic_review",
        idempotency_key="day9-hitl-review-proof",
        max_repairs=0,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "diagnostic_enrichment_enabled": True,
                "diagnostic_fixture_scenario": "diagnostic_clean_pass",
            },
        }
    )
    paused = orchestration.run(request)  # type: ignore[attr-defined]
    if paused.status != OrchestrationRunStatus.REVIEW_REQUIRED:
        return False
    mid = orchestration.run(  # type: ignore[attr-defined]
        request, resume=HumanResumeDecision(action="approve")
    )
    if mid.status != OrchestrationRunStatus.REVIEW_REQUIRED:
        return False
    payload = mid.metadata_json.get("interrupt_payload") or {}
    if not payload.get("diagnostic_results"):
        return False
    if not any(
        entry.get("review_required") for entry in (payload.get("diagnostic_validation") or [])
    ):
        return False
    approved = orchestration.run(  # type: ignore[attr-defined]
        request, resume=HumanResumeDecision(action="approve")
    )
    return bool(approved.status == OrchestrationRunStatus.COMPLETED)


def _injection_evidence_proof(orchestration: object, ctx: dict[str, str]) -> bool:
    from app.orchestration.fixtures import build_diagnostic_orchestration_request

    result = orchestration.run(  # type: ignore[attr-defined]
        build_diagnostic_orchestration_request(
            ctx,
            scenario="injection_evidence",
            idempotency_key="day9-injection-proof",
        )
    )
    injection_rev = ctx["injection_revision_id"]
    if result.status == OrchestrationRunStatus.COMPLETED:
        return bool(result.items) and all(item.marks == 1.0 for item in result.items) and all(
            injection_rev in item.source_revision_ids for item in result.items
        )
    if result.status != OrchestrationRunStatus.REVIEW_REQUIRED:
        return False
    payload = result.metadata_json.get("interrupt_payload") or {}
    deterministic = payload.get("deterministic_validation") or []
    return any("injection_evidence_control" in (d.get("issue_codes") or []) for d in deterministic)


def _service_proofs(service: DiagnosticIntelligenceService) -> dict[str, bool]:
    item = build_fixture_mcq_item()
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        competency_codes=["application"],
        learning_outcome_ids=["lo-fixture-1"],
        allowed_evidence_refs=["[CIT-1]"],
        allowed_source_revision_ids=item.source_revision_ids,
    )
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}
    tags = build_fixture_tags(item)
    tags[0] = tags[0].model_copy(
        update={
            "misconception_code": "MATH.ADD.WHOLE.SUM_AS_NEXT",
            "diagnostic_signal": "successor",
            "metadata_json": {"option_text": "unrelated distractor text"},
        }
    )
    bad_signal = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=request.taxonomy_version,
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    dup_tags = build_fixture_tags(item)
    dup_tags[2] = dup_tags[2].model_copy(
        update={
            "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            "diagnostic_signal": "off-by-one-low",
        }
    )
    dup_tags[2].metadata_json["option_text"] = "11 off-by-one-low"
    duplicate = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=dup_tags,
            taxonomy_version=request.taxonomy_version,
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    empty = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=[],
            taxonomy_version=request.taxonomy_version,
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    redundant_item = build_fixture_mcq_item(item_id="redundant-proof")
    redundant_item = redundant_item.model_copy(
        update={
            "options": [
                redundant_item.options[0].model_copy(update={"text": "dup text"}),
                redundant_item.options[1],
                redundant_item.options[2].model_copy(update={"text": "dup text"}),
            ]
        }
    )
    redundant_request = request.model_copy(update={"item": redundant_item})
    redundant_tags = build_fixture_tags(redundant_item)
    redundant_tags[0].metadata_json = {}
    redundant_tags[2].metadata_json = {}
    redundant = service.validate_result(
        redundant_request,
        DistractorDiagnosticResult(
            item_id=redundant_item.item_id,
            question_type=redundant_item.question_type,
            option_tags=redundant_tags,
            taxonomy_version=request.taxonomy_version,
            source_revision_ids=redundant_item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    missing_sources = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=request.taxonomy_version,
            source_revision_ids=[],
        ),
        candidate_codes=codes,
    )
    empty_auth_request = request.model_copy(update={"allowed_source_revision_ids": []})
    empty_auth = service.validate_result(
        empty_auth_request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=request.taxonomy_version,
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes=codes,
    )
    stem_item = build_fixture_mcq_item(item_id="arith-mismatch-proof").model_copy(
        update={"stem_text": "Synthetic fixture: What is 8 + 5?"}
    )
    stem_request = DiagnosticAuthoringRequest(
        item=stem_item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=stem_item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )
    stem_tags = build_fixture_tags(stem_item)
    stem_verdict = service.validate_result(
        stem_request,
        DistractorDiagnosticResult(
            item_id=stem_item.item_id,
            question_type=stem_item.question_type,
            option_tags=stem_tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=stem_item.source_revision_ids,
        ),
        candidate_codes={
            c.misconception_code for c in resolve_misconception_candidates(stem_request)
        },
    )
    return {
        "signal_mismatch_rejected": "signal_text_mismatch" in bad_signal.issue_codes,
        "distinctness_enforced": "duplicate_misconception" in duplicate.issue_codes,
        "canonical_tag_completeness": empty.status.value != "pass",
        "canonical_option_text_integrity": "untrusted_option_text_metadata"
        in bad_signal.issue_codes,
        "redundant_canonical_text_enforced": "redundant_distractor" in redundant.issue_codes,
        "result_source_provenance_required": "result_source_revision_missing"
        in missing_sources.issue_codes,
        "source_authorization_empty_rejected": "source_authorization_unresolved"
        in empty_auth.issue_codes,
        "arithmetic_operand_context_mismatch": "signal_text_mismatch" in stem_verdict.issue_codes
        and stem_verdict.status.value != "pass",
    }


def _marks_edit_forbidden_proof(orchestration: object, ctx: dict[str, str]) -> bool:
    from app.orchestration.fixtures import build_orchestration_request
    from app.orchestration.human_decision import HumanResumeDecision

    request = build_orchestration_request(
        ctx, scenario="human_review", idempotency_key="day9-marks-forbidden-proof"
    )
    paused = orchestration.run(request)  # type: ignore[attr-defined]
    if paused.status != OrchestrationRunStatus.REVIEW_REQUIRED:
        return False
    item_id = paused.metadata_json["interrupt_payload"]["item_ids"][0]
    failed = orchestration.run(  # type: ignore[attr-defined]
        request,
        resume=HumanResumeDecision(action="edit", item_patches={item_id: {"marks": 99.0}}),
    )
    return bool(
        failed.status == OrchestrationRunStatus.FAILED
        and "human_edit_provenance_forbidden" in failed.errors
    )


def _foreign_injection_context_proof(
    orchestration: object, ctx: dict[str, str], foreign_revision_id: str
) -> bool:
    import json

    from app.orchestration.enums import GenerationNodeRole
    from app.orchestration.fixtures import build_orchestration_request

    foreign_id = foreign_revision_id
    gateway = getattr(getattr(orchestration, "dependencies", None), "gateway", None)
    if gateway is None:
        return False
    malicious = build_orchestration_request(
        ctx,
        scenario="injection_evidence",
        idempotency_key="day9-foreign-context-proof",
    )
    malicious = malicious.model_copy(
        update={
            "metadata_json": {
                **malicious.metadata_json,
                "injection_revision_id": foreign_id,
            },
        }
    )
    result = orchestration.run(malicious)  # type: ignore[attr-defined]
    state = orchestration.compiled_graph.get_state(  # type: ignore[attr-defined]
        {"configurable": {"thread_id": result.run_id}}
    )
    knowledge = state.values.get("knowledge_context") or {}
    evidence_ids = {
        str(entry.get("source_revision_id"))
        for entry in knowledge.get("evidence") or []
        if entry.get("source_revision_id")
    }
    if foreign_id in evidence_ids:
        return False
    if foreign_id in str(knowledge.get("bounded_text") or ""):
        return False
    for call in gateway.call_history():
        if call.call_context and call.call_context.role == GenerationNodeRole.AUTHOR:
            if foreign_id in json.dumps(call.parsed, default=str):
                return False
    return True


def _hitl_diagnostic_edit_revalidates(orchestration: object, ctx: dict[str, str]) -> bool:
    from app.orchestration.enums import GenerationNodeRole
    from app.orchestration.fixtures import build_orchestration_request
    from app.orchestration.human_decision import HumanResumeDecision

    gateway = getattr(getattr(orchestration, "dependencies", None), "gateway", None)
    if gateway is None:
        return False
    request = build_orchestration_request(
        ctx,
        scenario="non_arithmetic_diagnostic_review",
        idempotency_key="day9-hitl-edit-proof",
        max_repairs=0,
    )
    request = request.model_copy(
        update={
            "metadata_json": {
                **request.metadata_json,
                "diagnostic_enrichment_enabled": True,
                "diagnostic_fixture_scenario": "diagnostic_clean_pass",
            },
        }
    )
    if orchestration.run(request).status != OrchestrationRunStatus.REVIEW_REQUIRED:  # type: ignore[attr-defined]
        return False
    mid = orchestration.run(  # type: ignore[attr-defined]
        request, resume=HumanResumeDecision(action="approve")
    )
    if mid.status != OrchestrationRunStatus.REVIEW_REQUIRED:
        return False
    payload = mid.metadata_json.get("interrupt_payload") or {}
    item_ids = payload.get("item_ids") or []
    if not item_ids:
        return False
    calls_before = len(
        [
            c
            for c in gateway.call_history()
            if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
        ]
    )
    edited = orchestration.run(  # type: ignore[attr-defined]
        request,
        resume=HumanResumeDecision(
            action="edit",
            item_patches={
                str(item_ids[0]): {
                    "stem_text": (
                        "Synthetic number-sense fixture: choose the best edited statement."
                    ),
                },
            },
        ),
    )
    if edited.status != OrchestrationRunStatus.REVIEW_REQUIRED:
        return False
    payload_after_edit = edited.metadata_json.get("interrupt_payload") or {}
    if payload_after_edit.get("diagnostic_results"):
        return False
    orchestration.run(  # type: ignore[attr-defined]
        request, resume=HumanResumeDecision(action="approve")
    )
    calls_after = len(
        [
            c
            for c in gateway.call_history()
            if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
        ]
    )
    return calls_after > calls_before


def build_verification_report(session: Session) -> dict[str, object]:
    scope_guard = verify_day9_scope_guard()
    day8_scope = verify_day8_scope_guard()
    taxonomy = load_taxonomy()
    service = DiagnosticIntelligenceService()
    run_positive_fixture_validation(service, allowed_refs=["[CIT-1]"])
    service_proofs = _service_proofs(service)

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
    forged = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_forged_evidence",
            idempotency_key="day9-forged-evidence-key",
        )
    )
    session.commit()
    tenant_isolation_ok, foreign_org_revision_id = _tenant_isolation_proof(
        orchestration, ctx, session
    )
    hitl_diagnostic_review_ok = _hitl_diagnostic_review_proof(orchestration, ctx)
    hitl_diagnostic_edit_ok = _hitl_diagnostic_edit_revalidates(orchestration, ctx)
    marks_edit_forbidden_ok = _marks_edit_forbidden_proof(orchestration, ctx)
    foreign_injection_context_ok = _foreign_injection_context_proof(
        orchestration, ctx, foreign_org_revision_id
    )
    injection_evidence_ok = _injection_evidence_proof(orchestration, ctx)
    checkpoint_restart_ok = prove_interrupted_diagnostic_checkpoint_restart()
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
    first_result = diagnostic_results[0] if diagnostic_results else {}
    audit_refs = first_result.get("audit_refs") or []
    audit_ref = audit_refs[0] if audit_refs else None
    audit_event = session.get(OrchestrationAuditEvent, audit_ref) if audit_ref else None

    candidate_sha, head_sha, sha_checks = _candidate_sha_checks()
    checks = {
        "scope_guard_ok": scope_guard.get("ok") is True,
        "day8_scope_guard_ok": day8_scope.get("ok") is True,
        "taxonomy_resolves": bool(taxonomy.misconceptions),
        "option_tags_produced": bool(option_tags),
        "correct_option_protected": correct_protected,
        "day6_authority_survives": blocked.status == OrchestrationRunStatus.FAILED,
        "forged_evidence_rejected": forged.status == OrchestrationRunStatus.FAILED,
        "tenant_isolation_enforced": tenant_isolation_ok,
        "hitl_diagnostic_review_proof": hitl_diagnostic_review_ok,
        "hitl_diagnostic_edit_revalidates": hitl_diagnostic_edit_ok,
        "marks_edit_forbidden": marks_edit_forbidden_ok,
        "foreign_injection_not_in_context": foreign_injection_context_ok,
        "injection_evidence_bounded": injection_evidence_ok,
        "checkpoint_explicit_retry_proof": checkpoint_restart_ok,
        "bounded_repair_works": repaired.status == OrchestrationRunStatus.COMPLETED
        and any((repaired.repair_summary or {}).values()),
        "unknown_code_rejected": unknown.status == OrchestrationRunStatus.FAILED,
        "idempotent_replay": replay.run_id == clean.run_id,
        "idempotency_conflict_guard": idem_conflict_ok,
        "diagnostic_audit_persisted": audit_event is not None
        and audit_event.payload_json.get("diagnostic") is True,
        "single_orchestration_graph": "diagnostic_repair" in str(
            orchestration.compiled_graph.get_graph().nodes
        ),
        **service_proofs,
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
