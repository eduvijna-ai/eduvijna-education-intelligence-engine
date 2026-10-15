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
from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
from app.orchestration.contracts import DraftQuestionItem, QuestionOptionDraft, ResolvedScope
from app.orchestration.enums import GenerationNodeRole
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.nodes.diagnostic import diagnostic_enrich_node


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


def _diag_results(result) -> list[dict]:
    return list(result.metadata_json.get("diagnostic_results") or [])


def _diagnostic_node_state(
    ctx: dict[str, str],
    request,
    draft: DraftQuestionItem,
) -> dict:
    return {
        "run_id": "day9-preflight-run",
        "request": request.model_dump(mode="json"),
        "draft_items": [draft.model_dump(mode="json")],
        "resolved_scope": ResolvedScope(
            curriculum_version_id=ctx["curriculum_version_id"],
            subject_code="mathematics",
            grade_year_code="grade-8",
            medium_code="english",
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            topic_codes=list(request.topic_codes),
            concept_codes=list(request.concept_codes),
        ).model_dump(mode="json"),
        "knowledge_context": KnowledgeContextPack(
            query_id="day9-preflight",
            query_text="fixture",
            retrieval_profile_version="ki-retrieval-v1",
            evidence=[],
            citations=[],
            scope=AppliedKnowledgeScope(
                organization_id=ctx["organization_id"],
                institution_id=ctx["institution_id"],
                curriculum_version_id=ctx["curriculum_version_id"],
            ),
            warnings=[],
            bounded_text="",
        ).model_dump(mode="json"),
        "solver_results": [],
        "diagnostic_validation": [],
        "diagnostic_results": [],
        "repair_count_by_item": {},
        "generation_call_cache": {},
        "gateway_usage": {},
    }


def test_diagnostic_enrich_node_preflight_unsupported_and_cardinality() -> None:
    session = _memory_session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_diagnostic_orchestration_request(
        ctx,
        idempotency_key="day9-node-preflight",
    )
    unsupported = DraftQuestionItem(
        item_id="item-unsupported",
        slot_index=0,
        stem_text="Synthetic",
        question_type="essay",
        options=[
            QuestionOptionDraft(option_key="A", text="11", is_correct=False),
            QuestionOptionDraft(option_key="B", text="12", is_correct=True),
        ],
        source_revision_ids=[ctx["official_revision_id"]],
        learning_outcome_ids=[ctx["learning_outcome_id"]],
        competency_codes=["application"],
        marks=1.0,
    )
    update = diagnostic_enrich_node(
        _diagnostic_node_state(ctx, request, unsupported),
        service.dependencies,
    )
    assert _diag_calls(gateway) == 0
    dr = update.get("diagnostic_results") or []
    assert dr[0]["aggregate_status"] == "not_applicable"
    assert "unsupported_question_type" in dr[0].get("warnings", [])
    assert dr[0].get("audit_refs")

    double = unsupported.model_copy(
        update={
            "item_id": "item-double",
            "question_type": "single_choice",
            "options": [
                QuestionOptionDraft(option_key="A", text="11", is_correct=True),
                QuestionOptionDraft(option_key="B", text="12", is_correct=True),
            ],
        }
    )
    update2 = diagnostic_enrich_node(
        _diagnostic_node_state(ctx, request, double),
        service.dependencies,
    )
    assert _diag_calls(gateway) == 0
    dr2 = update2.get("diagnostic_results") or []
    assert dr2[0]["aggregate_status"] == "reject"
    assert "correct_cardinality_invalid" in dr2[0].get("errors", [])
    session.close()


def test_diagnostic_enrich_node_preflight_missing_scope_and_no_candidates() -> None:
    session = _memory_session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_diagnostic_orchestration_request(
        ctx,
        idempotency_key="day9-node-preflight-scope",
    )
    draft = DraftQuestionItem(
        item_id="item-scope",
        slot_index=0,
        stem_text="Synthetic",
        question_type="single_choice",
        options=[
            QuestionOptionDraft(option_key="A", text="11", is_correct=False),
            QuestionOptionDraft(option_key="B", text="12", is_correct=True),
        ],
        source_revision_ids=[ctx["official_revision_id"]],
        learning_outcome_ids=[],
        competency_codes=[],
        marks=1.0,
    )
    scope_request = request.model_copy(
        update={"topic_codes": [], "concept_codes": [], "subject_code": "", "grade_year_code": ""}
    )
    missing_state = _diagnostic_node_state(ctx, scope_request, draft)
    missing_state["resolved_scope"] = ResolvedScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    ).model_dump(mode="json")
    update = diagnostic_enrich_node(missing_state, service.dependencies)
    assert _diag_calls(gateway) == 0
    dr = update.get("diagnostic_results") or []
    assert "missing_diagnostic_scope" in dr[0].get("warnings", [])

    gateway_b = FakeGenerationGateway()
    service.dependencies.gateway = gateway_b
    narrow = request.model_copy(update={"subject_code": "zz-no-misconception-subject"})
    narrow_state = _diagnostic_node_state(ctx, narrow, draft)
    narrow_state["resolved_scope"]["subject_code"] = "zz-no-misconception-subject"
    update2 = diagnostic_enrich_node(narrow_state, service.dependencies)
    assert _diag_calls(gateway_b) == 0
    dr2 = update2.get("diagnostic_results") or []
    assert "no_misconception_candidates" in dr2[0].get("warnings", [])
    session.close()


def test_orchestration_preflight_unknown_taxonomy_zero_calls() -> None:
    session = _memory_session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    request = build_diagnostic_orchestration_request(
        ctx,
        idempotency_key="day9-preflight-unknown-taxonomy",
        diagnostic_taxonomy_version="missing-taxonomy@v9",
    )
    result = service.run(request)
    assert _diag_calls(gateway) == 0
    dr = _diag_results(result)
    assert dr and "unknown_taxonomy_version" in dr[0].get("errors", [])
    session.close()


def test_preflight_unknown_taxonomy_version_unit() -> None:
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
