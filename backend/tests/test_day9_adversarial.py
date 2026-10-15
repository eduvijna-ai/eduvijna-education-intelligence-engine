from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.fixtures import build_fixture_mcq_item, build_fixture_tags
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.orchestration.enums import OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _authoring(item_id: str = "adv-1") -> DiagnosticAuthoringRequest:
    item = build_fixture_mcq_item(item_id=item_id)
    return DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=item.source_revision_ids,
        allowed_evidence_refs=["[CIT-1]"],
    )


def _codes(request: DiagnosticAuthoringRequest) -> set[str]:
    return {c.misconception_code for c in resolve_misconception_candidates(request)}


def test_adversarial_unknown_misconception_code() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring()
    wrong = request.item.options[0]
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=[
            OptionDiagnosticTag(
                item_id=request.item.item_id,
                option_key=wrong.option_key,
                is_correct=False,
                misconception_code="MATH.HALLUCINATED",
                diagnostic_signal="fake",
                metadata_json={"option_text": wrong.text},
            )
        ],
    )
    verdict = service.validate_result(request, result, candidate_codes=_codes(request))
    assert verdict.blocking is True


def test_adversarial_inactive_misconception() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-inactive")
    tags = build_fixture_tags(request.item)
    tags[0] = tags[0].model_copy(
        update={"misconception_code": "MATH.ADD.WHOLE.INACTIVE_SAMPLE"}
    )
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=tags,
    )
    codes = _codes(request) | {"MATH.ADD.WHOLE.INACTIVE_SAMPLE"}
    verdict = service.validate_result(request, result, candidate_codes=codes)
    assert "inactive_misconception" in verdict.issue_codes


def test_adversarial_forged_evidence_ref() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-2")
    wrong = request.item.options[0]
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=[
            OptionDiagnosticTag(
                item_id=request.item.item_id,
                option_key=wrong.option_key,
                is_correct=False,
                misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                diagnostic_signal="off-by-one-low",
                evidence_refs=["FORGED"],
                metadata_json={"option_text": wrong.text},
            )
        ],
    )
    verdict = service.validate_result(request, result, candidate_codes=_codes(request))
    assert "forged_evidence_ref" in verdict.issue_codes


def test_adversarial_duplicate_misconception_tags() -> None:
    service = DiagnosticIntelligenceService()
    request = _authoring("adv-dup")
    tags = build_fixture_tags(request.item)
    tags[2] = tags[2].model_copy(
        update={
            "misconception_code": "MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            "diagnostic_signal": "off-by-one-low",
        }
    )
    tags[2].metadata_json["option_text"] = "11 off-by-one-low"
    result = DistractorDiagnosticResult(
        item_id=request.item.item_id,
        question_type=request.item.question_type,
        option_tags=tags,
    )
    verdict = service.validate_result(request, result, candidate_codes=_codes(request))
    assert "duplicate_misconception" in verdict.issue_codes


def test_orchestration_rejects_unknown_diagnostic_code() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_unknown_code",
            idempotency_key="day9-adv-unknown",
        )
    )
    assert result.status == OrchestrationRunStatus.FAILED
    session.close()


def test_orchestration_rejects_inactive_and_correct_mislabeled() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    inactive = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_inactive",
            idempotency_key="day9-adv-inactive",
        )
    )
    mislabeled = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_correct_mislabeled",
            idempotency_key="day9-adv-mislabel",
        )
    )
    assert inactive.status == OrchestrationRunStatus.FAILED
    assert mislabeled.status == OrchestrationRunStatus.FAILED
    session.close()


def test_orchestration_gateway_timeout_401_5xx() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    timeout = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="gateway_timeout",
            idempotency_key="day9-adv-timeout",
        )
    )
    unauthorized = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="gateway_401",
            idempotency_key="day9-adv-401",
        )
    )
    unavailable = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="gateway_5xx",
            idempotency_key="day9-adv-5xx",
        )
    )
    assert timeout.status == OrchestrationRunStatus.RETRY_REQUIRED
    assert unauthorized.status == OrchestrationRunStatus.FAILED
    assert unavailable.status == OrchestrationRunStatus.RETRY_REQUIRED
    session.close()

