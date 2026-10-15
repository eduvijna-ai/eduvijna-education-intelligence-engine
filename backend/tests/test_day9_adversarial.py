from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.fixtures import build_fixture_mcq_item
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
    verdict = service.validate_result(request, result)
    assert verdict.blocking is True


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
    verdict = service.validate_result(request, result)
    assert "forged_evidence_ref" in verdict.issue_codes


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


def test_orchestration_gateway_timeout_semantics() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            scenario="gateway_timeout",
            diagnostic_scenario="diagnostic_clean_pass",
            idempotency_key="day9-adv-timeout",
        )
    )
    assert result.status in {
        OrchestrationRunStatus.RETRY_REQUIRED,
        OrchestrationRunStatus.FAILED,
    }
    session.close()
