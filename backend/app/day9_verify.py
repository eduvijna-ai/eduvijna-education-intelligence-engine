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
    bypass_item = build_fixture_mcq_item(item_id="day9-metadata-bypass").model_copy(
        update={
            "metadata_json": {"synthetic_fixture": True},
            "source_revision_ids": ["00000000-0000-0000-0000-000000000088"],
        }
    )
    bypass_request = DiagnosticAuthoringRequest(
        item=bypass_item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=bypass_item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )
    bypass_tags = build_fixture_tags(bypass_item)
    bypass_tags[0] = bypass_tags[0].model_copy(update={"evidence_refs": []})
    bypass_verdict = service.validate_result(
        bypass_request,
        DistractorDiagnosticResult(
            item_id=bypass_item.item_id,
            question_type=bypass_item.question_type,
            option_tags=bypass_tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=bypass_item.source_revision_ids,
        ),
        candidate_codes={
            c.misconception_code for c in resolve_misconception_candidates(bypass_request)
        },
    )

    return {
        "metadata_synthetic_flag_cannot_waive_evidence": "missing_diagnostic_evidence"
        in bypass_verdict.issue_codes,
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
        "sourceless_result_source_spoof_rejected": _sourceless_spoof_rejected(service),
        "foreign_grounding_preflight_rejected": _foreign_grounding_preflight_rejected(),
        "aggregate_evidence_budget_enforced": _aggregate_evidence_budget_enforced(),
        "decimal_wrong_answer_signal_rejected": _decimal_wrong_answer_signal_rejected(service),
    }


def _foreign_grounding_preflight_rejected() -> bool:
    from app.diagnostic_intelligence.contracts import Day7DiagnosticEvidenceSnippet
    from app.diagnostic_intelligence.preflight import run_diagnostic_preflight

    rev_a = "00000000-0000-0000-0000-0000000000aa"
    rev_b = "00000000-0000-0000-0000-0000000000bb"
    item = build_fixture_mcq_item(item_id="day9-verify-rev-ground").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=["[CIT-A]"],
        bounded_day7_context=f"[CIT-A] (revision {rev_a})",
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-X]",
                source_revision_id=rev_b,
                snippet="FOREIGN-UNTRUSTED-MARKER",
            )
        ],
    )
    preflight = run_diagnostic_preflight(request)
    return (
        not preflight.allow_model_call
        and (
            "unauthorized_source_revision" in preflight.issue_codes
            or "forged_evidence_ref" in preflight.issue_codes
        )
    )


def _aggregate_evidence_budget_enforced() -> bool:
    from pydantic import ValidationError

    from app.diagnostic_intelligence.contracts import Day7DiagnosticEvidenceSnippet

    rev_a = "REV-A"
    try:
        DiagnosticAuthoringRequest(
            item=build_fixture_mcq_item().model_copy(update={"source_revision_ids": [rev_a]}),
            subject_code="mathematics",
            grade_year_code="grade-8",
            topic_codes=["whole-numbers"],
            concept_codes=["addition-whole"],
            allowed_source_revision_ids=[rev_a],
            allowed_evidence_refs=["[CIT-A]"],
            bounded_day7_context="x" * 4000,
            day7_evidence_snippets=[
                Day7DiagnosticEvidenceSnippet(
                    citation_label="[CIT-A]",
                    source_revision_id=rev_a,
                    snippet="y" * 400,
                )
            ],
        )
    except ValidationError:
        return True
    return False


def _decimal_wrong_answer_signal_rejected(service: DiagnosticIntelligenceService) -> bool:
    item = build_fixture_mcq_item(item_id="day9-decimal-119", wrong_a="11.9")
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )
    tags = build_fixture_tags(item)
    tags[0].metadata_json["option_text"] = "11.9"
    verdict = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=item.source_revision_ids,
        ),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    return verdict.status.value != "pass" and "signal_text_mismatch" in verdict.issue_codes


def _spec_closure_proofs() -> dict[str, bool]:
    from sqlalchemy import create_engine

    from app.orchestration.enums import GenerationNodeRole
    from app.orchestration.gateway.fake import FakeGenerationGateway
    from app.orchestration.gateway.request_capture import RequestCapturingGateway

    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine)

    service = DiagnosticIntelligenceService()
    source_item = build_fixture_mcq_item(item_id="day9-verify-source-backed").model_copy(
        update={
            "metadata_json": {},
            "source_revision_ids": ["00000000-0000-0000-0000-000000000099"],
        }
    )
    source_request = DiagnosticAuthoringRequest(
        item=source_item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=source_item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )
    source_tags = build_fixture_tags(source_item)
    source_tags[0] = source_tags[0].model_copy(update={"evidence_refs": []})
    missing_evidence = service.validate_result(
        source_request,
        DistractorDiagnosticResult(
            item_id=source_item.item_id,
            question_type=source_item.question_type,
            option_tags=source_tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=source_item.source_revision_ids,
        ),
        candidate_codes={
            c.misconception_code for c in resolve_misconception_candidates(source_request)
        },
    )

    pass_item = build_fixture_mcq_item(item_id="day9-verify-verdict-fields")
    pass_request = DiagnosticAuthoringRequest(
        item=pass_item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=pass_item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )
    pass_verdict = service.validate_result(
        pass_request,
        DistractorDiagnosticResult(
            item_id=pass_item.item_id,
            question_type=pass_item.question_type,
            option_tags=build_fixture_tags(pass_item),
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=pass_item.source_revision_ids,
        ),
        candidate_codes={
            c.misconception_code for c in resolve_misconception_candidates(pass_request)
        },
    )
    wrong_option = next(v for v in pass_verdict.items if v.option_key == "A")

    inner = FakeGenerationGateway()
    capturing = RequestCapturingGateway(inner)
    ctx, orchestration = build_day8_test_service(session, gateway=capturing)
    bounded_run = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-verify-bounded-day7",
        )
    )
    diag_requests = [
        r for r in capturing.captured_requests() if r.role == GenerationNodeRole.DIAGNOSTIC
    ]
    bounded_ok = False
    if diag_requests and bounded_run.status == OrchestrationRunStatus.COMPLETED:
        payload = diag_requests[0].user_payload
        bounded = str(payload.get("bounded_day7_context") or "").strip()
        bounded_ok = bool(bounded) and "ignore previous instructions" not in bounded.lower()

    usage_run = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-verify-usage-batch",
            requested_count=2,
        )
    )
    usage = usage_run.gateway_usage or {}
    by_role = usage.get("model_calls_by_role") or {}
    usage_ok = (
        usage_run.status == OrchestrationRunStatus.COMPLETED
        and int(by_role.get("diagnostic", 0)) == 3
        and float(usage.get("diagnostic_validator_ms", 0)) > 0
    )

    audit_run = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-verify-option-audit",
        )
    )
    option_traces_ok = False
    if audit_run.status == OrchestrationRunStatus.COMPLETED:
        diag = (audit_run.metadata_json.get("diagnostic_results") or [])[0]
        audit_ref = (diag.get("audit_refs") or [None])[0]
        event = session.get(OrchestrationAuditEvent, audit_ref) if audit_ref else None
        traces = (event.payload_json.get("option_traces") if event else None) or []
        option_traces_ok = bool(traces) and any(t.get("option_key") for t in traces)

    redundant_item = build_fixture_mcq_item(
        item_id="day9-verify-coverage", wrong_a="11", wrong_b="11.0"
    )
    redundant_request = DiagnosticAuthoringRequest(
        item=redundant_item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=redundant_item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )
    rtags = build_fixture_tags(redundant_item)
    rtags[0].metadata_json["option_text"] = "11"
    rtags[2].metadata_json["option_text"] = "11.0"
    rtags[2] = rtags[2].model_copy(
        update={
            "misconception_code": "MATH.ADD.WHOLE.DOUBLE_OPERAND",
            "diagnostic_signal": "double",
        }
    )
    redundant_result = DistractorDiagnosticResult(
        item_id=redundant_item.item_id,
        question_type=redundant_item.question_type,
        option_tags=rtags,
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
        source_revision_ids=redundant_item.source_revision_ids,
    )
    redundant_verdict = service.validate_result(
        redundant_request,
        redundant_result,
        candidate_codes={
            c.misconception_code for c in resolve_misconception_candidates(redundant_request)
        },
    )

    proofs = {
        "diagnostic_bounded_day7_in_gateway": bounded_ok,
        "source_backed_missing_evidence_rejected": "missing_diagnostic_evidence"
        in missing_evidence.issue_codes,
        "coverage_complete_tracks_validator": redundant_result.coverage_summary is not None
        and not redundant_result.coverage_summary.coverage_complete
        and "redundant_distractor" in redundant_verdict.issue_codes,
        "verdict_option_fields_populated": bool(wrong_option.field_paths)
        and bool(wrong_option.misconception_code),
        "diagnostic_audit_option_traces": option_traces_ok,
        "diagnostic_role_usage_accounting": usage_ok,
    }
    session.close()
    return proofs


def _sourceless_spoof_rejected(service: DiagnosticIntelligenceService) -> bool:
    item = build_fixture_mcq_item(item_id="day9-sourceless-spoof").model_copy(
        update={"source_revision_ids": []}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[],
        allowed_evidence_refs=["[CIT-1]"],
    )
    tags = build_fixture_tags(item)
    codes = {c.misconception_code for c in resolve_misconception_candidates(request)}
    verdict = service.validate_result(
        request,
        DistractorDiagnosticResult(
            item_id=item.item_id,
            question_type=item.question_type,
            option_tags=tags,
            taxonomy_version=DEFAULT_TAXONOMY_VERSION,
            source_revision_ids=["FOREIGN-REVISION"],
        ),
        candidate_codes=codes,
    )
    return (
        verdict.status.value != "pass"
        and verdict.blocking
        and "result_source_revision_mismatch" in verdict.issue_codes
    )


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


def _foreign_injection_context_proof() -> bool:
    import json
    import tempfile

    from app.orchestration.enums import GenerationNodeRole
    from app.orchestration.fixtures import build_day8_test_service, build_orchestration_request
    from app.orchestration.gateway.fake import FakeGenerationGateway
    from app.orchestration.gateway.request_capture import RequestCapturingGateway

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/foreign-inj-proof.db")
        enable_sqlite_foreign_keys(engine)
        Base.metadata.create_all(engine)
        with Session(engine) as proof_session:
            capturing = RequestCapturingGateway(FakeGenerationGateway())
            ctx, orchestration = build_day8_test_service(proof_session, gateway=capturing)
            foreign = seed_day9_foreign_tenant_revisions(proof_session, ctx)
            foreign_id = foreign.foreign_organization_revision_id
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
            result = orchestration.run(malicious)
            state = orchestration.compiled_graph.get_state(
                {"configurable": {"thread_id": result.run_id}}
            )
            knowledge = state.values.get("knowledge_context") or {}
            evidence_ids = {
                str(entry.get("source_revision_id"))
                for entry in knowledge.get("evidence") or []
                if entry.get("source_revision_id")
            }
            bounded = str(knowledge.get("bounded_text") or "")
            if foreign_id in evidence_ids or foreign_id in bounded or "DAY9-ORG-B" in bounded:
                return False
            author_calls = capturing.captured_for_role(GenerationNodeRole.AUTHOR)
            if not author_calls:
                return False
            for captured in author_calls:
                blob = json.dumps(captured.user_payload, default=str)
                if foreign_id in blob or "DAY9-ORG-B" in blob:
                    return False
                if foreign_id in captured.system_prompt or "DAY9-ORG-B" in captured.system_prompt:
                    return False
            curriculum_calls = capturing.captured_for_role(GenerationNodeRole.CURRICULUM_REVIEW)
            if not curriculum_calls:
                return False
            for captured in curriculum_calls:
                blob = json.dumps(captured.user_payload, default=str)
                if foreign_id in blob or "DAY9-ORG-B" in blob:
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
    closure_proofs = _spec_closure_proofs()

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
    tenant_isolation_ok, _ = _tenant_isolation_proof(orchestration, ctx, session)
    hitl_diagnostic_review_ok = _hitl_diagnostic_review_proof(orchestration, ctx)
    hitl_diagnostic_edit_ok = _hitl_diagnostic_edit_revalidates(orchestration, ctx)
    marks_edit_forbidden_ok = _marks_edit_forbidden_proof(orchestration, ctx)
    foreign_injection_context_ok = _foreign_injection_context_proof()
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
        **closure_proofs,
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
