"""Day 9 specification-closure acceptance (D9-CLOSE-01…08)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import DiagnosticAuthoringRequest
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
)
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.request_capture import RequestCapturingGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest


class _DiagnosticStageFailGateway:
    """Fail only DIAGNOSTIC-role calls with a gateway error (D9-30)."""

    def __init__(self, *, error_code: str, retryable: bool, http_status: int | None = None) -> None:
        self._inner = FakeGenerationGateway()
        self._error_code = error_code
        self._retryable = retryable
        self._http_status = http_status
        self._attempted: list[GenerationRequest] = []

    def call_history(self):
        return self._inner.call_history()

    def attempted_requests(self) -> list[GenerationRequest]:
        return list(self._attempted)

    def generate(self, request: GenerationRequest):
        if request.role == GenerationNodeRole.DIAGNOSTIC:
            self._attempted.append(request)
            raise GenerationGatewayError(
                self._error_code,
                f"simulated {self._error_code} at diagnostic stage",
                retryable=self._retryable,
                http_status=self._http_status,
            )
        return self._inner.generate(request)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_diagnostic_gateway_payload_includes_bounded_day7_evidence() -> None:
    session = _session()
    inner = FakeGenerationGateway()
    gateway = RequestCapturingGateway(inner)
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-close-bounded-evidence",
        )
    )
    assert result.status == OrchestrationRunStatus.COMPLETED
    diag_requests = [
        r
        for r in gateway.captured_requests()
        if r.role == GenerationNodeRole.DIAGNOSTIC
    ]
    assert diag_requests, "expected at least one DIAGNOSTIC generation request"
    payload = diag_requests[0].user_payload
    bounded = str(payload.get("bounded_day7_context") or "").strip()
    assert bounded, "bounded_day7_context must be populated from Day-7 pack"
    snippets = payload.get("day7_evidence_snippets") or []
    assert snippets, "day7_evidence_snippets must accompany bounded context"
    revision_ids = {str(s.get("source_revision_id")) for s in snippets}
    allowed = set(payload.get("allowed_source_revision_ids") or [])
    assert revision_ids.issubset(allowed | set(str(x) for x in allowed))
    assert "ignore previous instructions" not in bounded.lower()
    for snippet in snippets:
        body = str(snippet.get("snippet") or "")
        assert "ignore previous instructions" not in body.lower()
    blocked = set(payload.get("blocked_tenant_revision_ids") or [])
    injection_id = ctx.get("injection_revision_id")
    if injection_id:
        assert injection_id in blocked or injection_id not in revision_ids
    session.close()


def test_source_backed_item_requires_evidence_refs() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="source-backed-close").model_copy(
        update={
            "metadata_json": {},
            "source_revision_ids": ["00000000-0000-0000-0000-000000000099"],
        }
    )
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
    tags[0] = tags[0].model_copy(update={"evidence_refs": []})
    result = build_fixture_result(request.item, tags)
    verdict = service.validate_result(
        request,
        result,
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value != "pass"
    assert "missing_diagnostic_evidence" in verdict.issue_codes
    assert result.coverage_summary is not None
    assert result.coverage_summary.coverage_complete is False


def test_coverage_complete_false_when_redundant_numeric_meaning() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(
        item_id="coverage-numeric",
        wrong_a="11",
        wrong_b="11.0",
    )
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
    tags[0].metadata_json["option_text"] = "11"
    tags[2].metadata_json["option_text"] = "11.0"
    tags[2] = tags[2].model_copy(
        update={
            "misconception_code": "MATH.ADD.WHOLE.DOUBLE_OPERAND",
            "diagnostic_signal": "double",
        }
    )
    result = build_fixture_result(item, tags)
    verdict = service.validate_result(
        request,
        result,
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert "redundant_distractor" in verdict.issue_codes
    assert result.coverage_summary is not None
    assert result.coverage_summary.coverage_complete is False


def test_verdict_populates_option_level_fields() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="verdict-fields")
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
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value == "pass"
    wrong = next(v for v in verdict.items if v.option_key == "A")
    assert wrong.misconception_code == "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"
    assert wrong.evidence_refs == ["[CIT-1]"]
    assert wrong.field_paths


def test_audit_persists_option_traces() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            idempotency_key="day9-close-option-traces",
        )
    )
    assert result.status == OrchestrationRunStatus.COMPLETED
    diag = (result.metadata_json.get("diagnostic_results") or [])[0]
    audit_ref = diag["audit_refs"][0]
    event = session.get(OrchestrationAuditEvent, audit_ref)
    assert event is not None
    traces = event.payload_json.get("option_traces") or []
    assert traces
    wrong_trace = next(t for t in traces if not t.get("is_correct"))
    assert wrong_trace.get("misconception_code")
    assert wrong_trace.get("option_key")
    correct_trace = next(t for t in traces if t.get("is_correct"))
    assert not correct_trace.get("misconception_code")
    session.close()


def test_diagnostic_role_usage_accounting_in_batch() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-close-usage",
            requested_count=2,
        )
    )
    assert result.status == OrchestrationRunStatus.COMPLETED
    usage = result.gateway_usage or {}
    by_role = usage.get("model_calls_by_role") or {}
    assert int(by_role.get("diagnostic", 0)) == 3
    assert float(usage.get("diagnostic_validator_ms", 0)) > 0
    session.close()


def test_diagnostic_stage_gateway_timeout_retry_required() -> None:
    session = _session()
    gateway = _DiagnosticStageFailGateway(
        error_code="gateway_timeout", retryable=True
    )
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-close-diag-timeout",
        )
    )
    assert result.status == OrchestrationRunStatus.RETRY_REQUIRED
    assert "gateway_timeout" in (result.errors or [])
    attempted = gateway.attempted_requests()
    assert any(r.role == GenerationNodeRole.DIAGNOSTIC for r in attempted)
    usage = result.gateway_usage or {}
    failed = (usage.get("gateway_attempts_by_role") or {}).get("diagnostic", {})
    assert int(failed.get("failed", 0)) >= 1
    session.close()


def test_diagnostic_stage_gateway_401_failed() -> None:
    session = _session()
    gateway = _DiagnosticStageFailGateway(
        error_code="gateway_unauthorized", retryable=False, http_status=401
    )
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-close-diag-401",
        )
    )
    assert result.status == OrchestrationRunStatus.FAILED
    assert any(r.role == GenerationNodeRole.DIAGNOSTIC for r in gateway.attempted_requests())
    session.close()


def test_diagnostic_stage_gateway_5xx_retry_required() -> None:
    session = _session()
    gateway = _DiagnosticStageFailGateway(
        error_code="gateway_unavailable", retryable=True, http_status=503
    )
    ctx, service = build_day8_test_service(session, gateway=gateway)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-close-diag-5xx",
        )
    )
    assert result.status == OrchestrationRunStatus.RETRY_REQUIRED
    assert any(r.role == GenerationNodeRole.DIAGNOSTIC for r in gateway.attempted_requests())
    session.close()


def test_orchestration_diagnostic_malformed_output_blocks() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_malformed_output",
            idempotency_key="day9-close-malformed-diag",
            max_repairs=0,
        )
    )
    assert result.status == OrchestrationRunStatus.FAILED
    assert any(
        "model_schema_invalid" in str(err).lower() or "schema" in str(err).lower()
        for err in (result.errors or [])
    )
    session.close()


def test_canonical_second_correct_distractor_text() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="second-correct-canonical", wrong_a="12")
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
    tags[0].metadata_json["option_text"] = "12"
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert "second_correct_distractor" in verdict.issue_codes
