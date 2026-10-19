"""Day 9 spec-closure repair round 2 (D9-SC-R2-01…05)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    Day7DiagnosticEvidenceSnippet,
    DiagnosticAuthoringRequest,
)
from app.diagnostic_intelligence.enrichment import build_gateway_user_payload
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
    with_fixture_day7_evidence,
)
from app.diagnostic_intelligence.grounding import validate_diagnostic_grounding
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.diagnostic_intelligence.verdict import status_for_issue_codes
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.request_capture import RequestCapturingGateway
from app.orchestration.usage import merge_gateway_usage


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _rev_a_grounded_request(
    *,
    snippets: list[Day7DiagnosticEvidenceSnippet],
    bounded: str,
) -> DiagnosticAuthoringRequest:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    item = build_fixture_mcq_item(item_id="sc-r2-ground").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    trusted = {s.citation_label: s.source_revision_id for s in snippets}
    return DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=list(trusted.keys()) or ["[CIT-A]"],
        bounded_day7_context=bounded,
        day7_evidence_snippets=snippets,
        trusted_citation_revision_map=trusted,
    )


def test_preflight_rejects_foreign_rev_b_snippet() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    rev_b = "00000000-0000-0000-0000-0000000000bb"
    request = _rev_a_grounded_request(
        bounded=f"[CIT-A] (revision {rev_a})",
        snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-X]",
                source_revision_id=rev_b,
                snippet="FOREIGN-UNTRUSTED-MARKER",
            )
        ],
    )
    issues = validate_diagnostic_grounding(request)
    assert "unauthorized_source_revision" in issues or "forged_evidence_ref" in issues
    preflight = run_diagnostic_preflight(request)
    assert preflight.allow_model_call is False
    assert (
        "unauthorized_source_revision" in preflight.issue_codes
        or "forged_evidence_ref" in preflight.issue_codes
        or "insufficient_diagnostic_grounding" in preflight.issue_codes
    )


def test_preflight_rejects_bounded_index_without_matching_snippet() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    request = _rev_a_grounded_request(
        bounded=f"[CIT-A] (revision {rev_a})",
        snippets=[],
    )
    preflight = run_diagnostic_preflight(request)
    assert preflight.allow_model_call is False
    assert "insufficient_diagnostic_grounding" in preflight.issue_codes


def test_preflight_allows_matching_rev_a_snippet() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    request = _rev_a_grounded_request(
        bounded=f"[CIT-A] (revision {rev_a})",
        snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-A]",
                source_revision_id=rev_a,
                snippet="approved grounding snippet",
            )
        ],
    )
    preflight = run_diagnostic_preflight(request)
    assert preflight.allow_model_call is True
    payload = build_gateway_user_payload(request)
    assert "approved grounding snippet" in json.dumps(payload)


def test_orchestration_preflight_foreign_grounding_no_diagnostic_gateway() -> None:
    session = _session()
    capturing = RequestCapturingGateway(FakeGenerationGateway())
    ctx, orchestration = build_day8_test_service(session, gateway=capturing)
    item = build_fixture_mcq_item(item_id="orch-ground-block").model_copy(
        update={
            "source_revision_ids": ["00000000-0000-0000-0000-000000000099"],
            "metadata_json": {"sc_r2_bad_grounding": True},
        }
    )
    rev_a = item.source_revision_ids[0]
    rev_b = "00000000-0000-0000-0000-0000000000bb"
    bad_authoring = DiagnosticAuthoringRequest(
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
    preflight = run_diagnostic_preflight(bad_authoring)
    assert not preflight.allow_model_call
    result = orchestration.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="sc-r2-preflight-audit",
        )
    )
    assert result.status in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.REVIEWING,
        OrchestrationRunStatus.REVIEW_REQUIRED,
    }
    diagnostic_calls = capturing.captured_for_role(GenerationNodeRole.DIAGNOSTIC)
    marker = "FOREIGN-UNTRUSTED-MARKER"
    assert all(marker not in json.dumps(c.user_payload) for c in diagnostic_calls)
    session.close()


def test_aggregate_evidence_budget_rejects_4000_plus_snippets() -> None:
    rev_a = "REV-A"
    with pytest.raises(ValidationError, match="diagnostic_evidence_budget_exceeded"):
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


def test_decimal_option_11_9_rejects_off_by_one_signal() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="decimal-signal", wrong_a="11.9")
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
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value != "pass"
    assert "signal_text_mismatch" in verdict.issue_codes


def test_integer_11_and_descriptive_wrappers_still_pass_signal() -> None:
    service = DiagnosticIntelligenceService()
    for wrong_a in ("11", "11 off-by-one-low", "11.0"):
        item = build_fixture_mcq_item(item_id=f"ok-{wrong_a}", wrong_a=wrong_a)
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
        tags[0].metadata_json["option_text"] = wrong_a
        verdict = service.validate_result(
            request,
            build_fixture_result(item, tags),
            candidate_codes={
                c.misconception_code for c in resolve_misconception_candidates(request)
            },
        )
        assert "signal_text_mismatch" not in verdict.issue_codes


def test_mixed_repair_and_review_codes_aggregate_review_required() -> None:
    assert (
        status_for_issue_codes(["signal_text_mismatch", "plausibility_unverified"])
        == DiagnosticValidationStatus.REVIEW_REQUIRED
    )
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="mixed-severity", wrong_a="foo")
    request = with_fixture_day7_evidence(
        DiagnosticAuthoringRequest(
            item=item,
            subject_code="mathematics",
            grade_year_code="grade-8",
            topic_codes=["whole-numbers"],
            concept_codes=["addition-whole"],
            allowed_source_revision_ids=item.source_revision_ids,
            allowed_evidence_refs=["[CIT-1]"],
        )
    )
    tags = build_fixture_tags(item)
    tags[0].metadata_json["option_text"] = "foo"
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    option_a = next(v for v in verdict.items if v.option_key == "A")
    assert option_a.status == DiagnosticValidationStatus.REVIEW_REQUIRED
    assert verdict.status == DiagnosticValidationStatus.REVIEW_REQUIRED
    enriched = service.attach_validation_status(build_fixture_result(item, tags), verdict)
    assert enriched.option_tags[0].validation_status == DiagnosticValidationStatus.REVIEW_REQUIRED


def test_item_level_day6_block_propagates_to_wrong_options() -> None:
    from unittest.mock import MagicMock

    service = DiagnosticIntelligenceService(education_service=MagicMock())
    item = build_fixture_mcq_item(item_id="day6-item-block")
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
    with patch(
        "app.diagnostic_intelligence.service.day6_blocking_for_item",
        return_value=["day6_blocking"],
    ):
        verdict = service.validate_result(
            request,
            build_fixture_result(item, tags),
            candidate_codes={
                c.misconception_code for c in resolve_misconception_candidates(request)
            },
            scope=object(),  # type: ignore[arg-type]
            draft_item=object(),  # type: ignore[arg-type]
        )
    assert verdict.status == DiagnosticValidationStatus.REJECT
    wrong_entries = [v for v in verdict.items if v.option_key in {"A", "C"}]
    assert wrong_entries
    assert all(e.status == DiagnosticValidationStatus.REJECT for e in wrong_entries)
    assert all("day6_blocking" in e.issue_codes for e in wrong_entries)
    enriched = service.attach_validation_status(build_fixture_result(item, tags), verdict)
    assert all(
        t.validation_status == DiagnosticValidationStatus.REJECT
        for t in enriched.option_tags
        if not t.is_correct
    )


def test_token_usage_counts_accumulate_unknown_then_reported() -> None:
    usage: dict = {}
    usage = merge_gateway_usage(usage, {}, role="diagnostic")
    usage = merge_gateway_usage(
        usage, {"tokens_in": 10, "tokens_out": 5}, role="diagnostic"
    )
    counts = (usage.get("token_usage_counts_by_role") or {}).get("diagnostic") or {}
    assert int(counts.get("unknown", 0)) == 1
    assert int(counts.get("reported", 0)) == 1


def test_gateway_ambiguous_not_counted_as_failed_attempt() -> None:
    from app.orchestration.usage import record_gateway_role_ambiguous, record_gateway_role_attempt

    usage = record_gateway_role_ambiguous({}, "diagnostic")
    usage = record_gateway_role_attempt(usage, "diagnostic", succeeded=False)
    attempts = (usage.get("gateway_attempts_by_role") or {}).get("diagnostic") or {}
    ambiguous = (usage.get("gateway_ambiguous_by_role") or {}).get("diagnostic") or 0
    assert int(ambiguous) == 1
    assert int(attempts.get("failed", 0)) == 1
