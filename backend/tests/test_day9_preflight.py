from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DiagnosticQuestionItem,
    DiagnosticQuestionOption,
)
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.orchestration.gateway.fake import FakeGenerationGateway


def test_preflight_blocks_unsupported_type_without_gateway_call() -> None:
    gateway = FakeGenerationGateway()
    request = DiagnosticAuthoringRequest(
        item=DiagnosticQuestionItem(
            item_id="x",
            stem_text="Short answer?",
            question_type="short_answer",
            options=[],
        )
    )
    result = run_diagnostic_preflight(request)
    assert result.allow_model_call is False
    assert len(gateway.call_history()) == 0


def test_preflight_blocks_invalid_correct_cardinality() -> None:
    gateway = FakeGenerationGateway()
    request = DiagnosticAuthoringRequest(
        item=DiagnosticQuestionItem(
            item_id="x",
            stem_text="Pick one",
            question_type="single_choice",
            options=[
                DiagnosticQuestionOption(option_key="A", text="1", is_correct=True),
                DiagnosticQuestionOption(option_key="B", text="2", is_correct=True),
            ],
        )
    )
    result = run_diagnostic_preflight(request)
    assert result.allow_model_call is False
    assert result.blocking is True
    assert len(gateway.call_history()) == 0
