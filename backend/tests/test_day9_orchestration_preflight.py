from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DiagnosticQuestionItem,
    DiagnosticQuestionOption,
)
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.orchestration.enums import GenerationNodeRole, OrchestrationRunStatus
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway


def _diag_calls(gateway: FakeGenerationGateway) -> int:
    return len(
        [
            c
            for c in gateway.call_history()
            if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
        ]
    )


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_orchestration_preflight_blocks_invalid_cardinality() -> None:
    session = _memory_session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    double_correct = build_diagnostic_orchestration_request(
        ctx,
        scenario="double_correct",
        idempotency_key="day9-preflight-cardinality",
    )
    result = service.run(double_correct)
    assert _diag_calls(gateway) == 0
    assert result.status == OrchestrationRunStatus.FAILED
    session.close()


def test_preflight_unknown_taxonomy_version() -> None:
    item = DiagnosticQuestionItem(
        item_id="x",
        stem_text="What is 7 + 5?",
        question_type="single_choice",
        options=[
            DiagnosticQuestionOption(option_key="A", text="11", is_correct=False),
            DiagnosticQuestionOption(option_key="B", text="12", is_correct=True),
        ],
    )
    preflight = run_diagnostic_preflight(
        DiagnosticAuthoringRequest(
            item=item,
            subject_code="mathematics",
            grade_year_code="grade-8",
            topic_codes=["whole-numbers"],
            concept_codes=["addition-whole"],
            taxonomy_version="missing-taxonomy@v9",
        )
    )
    assert preflight.allow_model_call is False
    assert "unknown_taxonomy_version" in preflight.issue_codes
