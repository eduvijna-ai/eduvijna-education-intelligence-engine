"""Day 9 spec-closure repair round 5 (D9-SC-R5-01…03)."""

from __future__ import annotations

import uuid

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
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
    with_fixture_day7_evidence,
)
from app.diagnostic_intelligence.numeric_tokens import (
    has_unsupported_arithmetic_expression,
    numeric_literal_matches_integer,
)
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.knowledge_intelligence.contracts import (
    AppliedKnowledgeScope,
    KnowledgeContextPack,
    KnowledgeEvidenceItem,
)
from app.models.orchestration import OrchestrationAuditEvent
from app.orchestration.contracts import DraftQuestionItem, QuestionOptionDraft, ResolvedScope
from app.orchestration.enums import GenerationNodeRole
from app.orchestration.fixtures import (
    build_day8_test_service,
    build_diagnostic_orchestration_request,
)
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.nodes.diagnostic import diagnostic_enrich_node


def _evidence_item(index: int, revision: str, body: str) -> KnowledgeEvidenceItem:
    return KnowledgeEvidenceItem(
        source_id=f"src-{index}",
        source_revision_id=revision,
        source_revision_checksum=f"chk-{index}",
        binding_id=f"bind-{index}",
        trust_tier="approved",
        authority_label="fixture",
        title=f"title-{index}",
        locator=f"loc-{index}",
        snippet=body,
        retrieval_score=1.0,
        retrieval_rank=index,
        anythingllm_workspace="ws",
        anythingllm_document_id=f"doc-{index}",
        citation_label=f"[CIT-{index}]",
    )


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_source_backed_empty_trusted_map_rejects_allowlisted_citation() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    item = build_fixture_mcq_item(item_id="r5-unbound-empty-map").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=["[CIT-1]"],
        trusted_citation_revision_map={},
        day7_evidence_snippets=[],
    )
    tags = build_fixture_tags(item)
    verdict = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.blocking
    assert verdict.status.value != "pass"
    assert "unbound_diagnostic_evidence" in verdict.issue_codes


def test_source_backed_trusted_map_and_snippet_passes() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    item = build_fixture_mcq_item(item_id="r5-bound-pass").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=["[CIT-1]"],
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-1]",
                source_revision_id=rev_a,
                snippet="approved visible snippet",
            )
        ],
        trusted_citation_revision_map={"[CIT-1]": rev_a},
        bounded_day7_context=f"[CIT-1] (revision {rev_a})",
    )
    tags = build_fixture_tags(item)
    verdict = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value == "pass"


def test_source_backed_wrong_trusted_map_revision_rejected() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    rev_b = "00000000-0000-0000-0000-0000000000bb"
    item = build_fixture_mcq_item(item_id="r5-wrong-map").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=["[CIT-1]"],
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-1]",
                source_revision_id=rev_a,
                snippet="visible",
            )
        ],
        trusted_citation_revision_map={"[CIT-1]": rev_b},
    )
    tags = build_fixture_tags(item)
    verdict = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value != "pass"
    assert "unbound_diagnostic_evidence" in verdict.issue_codes


def test_source_free_generic_fixture_unaffected() -> None:
    item = build_fixture_mcq_item(item_id="r5-source-free").model_copy(
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
    for tag in tags:
        if not tag.is_correct:
            tag.evidence_refs = []
    verdict = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags, source_revision_ids=[]),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value == "pass"


def test_multiplication_and_ratio_expressions_rejected_by_numeric_helpers() -> None:
    for text in ("11 * 2", "11×2", "11:9", "(11*2)", "11 % 2", "11 ÷ 2"):
        assert has_unsupported_arithmetic_expression(text)
        assert not numeric_literal_matches_integer(text, 11)
    assert numeric_literal_matches_integer("11", 11)
    assert numeric_literal_matches_integer("11.0", 11)
    assert numeric_literal_matches_integer("11 off-by-one-low", 11)


def test_service_rejects_multiplication_expression_off_by_one_low() -> None:
    service = DiagnosticIntelligenceService()
    for option_text in ("11 * 2", "11×2", "11:9"):
        item = build_fixture_mcq_item(item_id=f"r5-expr-{option_text}", wrong_a=option_text)
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
        tags[0].metadata_json["option_text"] = option_text
        verdict = service.validate_result(
            request,
            build_fixture_result(item, tags),
            candidate_codes={
                c.misconception_code for c in resolve_misconception_candidates(request)
            },
        )
        assert verdict.status.value != "pass"
        assert (
            "signal_text_mismatch" in verdict.issue_codes
            or "plausibility_unverified" in verdict.issue_codes
        )


def test_diagnostic_enrich_node_eight_revision_truncation_e2e() -> None:
    session = _memory_session()
    gateway = FakeGenerationGateway()
    ctx, service = build_day8_test_service(session, gateway=gateway)
    revisions = [str(uuid.uuid4()) for _ in range(8)]
    pack = KnowledgeContextPack(
        query_id="r5-e2e-multi",
        query_text="multi",
        retrieval_profile_version="ki-retrieval-v1",
        evidence=[_evidence_item(i + 1, revisions[i], "x" * 512) for i in range(8)],
        citations=[],
        scope=AppliedKnowledgeScope(
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            curriculum_version_id=ctx["curriculum_version_id"],
        ),
        warnings=[],
        bounded_text="",
    )
    orch_request = build_diagnostic_orchestration_request(
        ctx,
        idempotency_key="day9-sc-r5-e2e-eight",
    )
    draft = DraftQuestionItem(
        item_id="item-eight-src",
        slot_index=0,
        stem_text="Synthetic fixture: What is 7 + 5?",
        question_type="single_choice",
        options=[
            QuestionOptionDraft(option_key="A", text="11 off-by-one-low", is_correct=False),
            QuestionOptionDraft(option_key="B", text="12", is_correct=True),
            QuestionOptionDraft(option_key="C", text="13 successor", is_correct=False),
        ],
        source_revision_ids=revisions,
        learning_outcome_ids=[ctx["learning_outcome_id"]],
        competency_codes=["application"],
        marks=1.0,
    )
    state = {
        "run_id": "day9-sc-r5-e2e",
        "request": orch_request.model_dump(mode="json"),
        "draft_items": [draft.model_dump(mode="json")],
        "resolved_scope": ResolvedScope(
            curriculum_version_id=ctx["curriculum_version_id"],
            subject_code="mathematics",
            grade_year_code="grade-8",
            medium_code="english",
            organization_id=ctx["organization_id"],
            institution_id=ctx["institution_id"],
            topic_codes=list(orch_request.topic_codes),
            concept_codes=list(orch_request.concept_codes),
        ).model_dump(mode="json"),
        "knowledge_context": pack.model_dump(mode="json"),
        "solver_results": [],
        "diagnostic_validation": [],
        "diagnostic_results": [],
        "repair_count_by_item": {},
        "generation_call_cache": {},
        "gateway_usage": {},
    }
    update = diagnostic_enrich_node(state, service.dependencies)
    diag_calls = [
        c
        for c in gateway.call_history()
        if c.call_context and c.call_context.role == GenerationNodeRole.DIAGNOSTIC
    ]
    assert diag_calls == []
    validation = (update.get("diagnostic_validation") or [])[0]
    assert "unauthorized_source_revision" not in validation.get("issue_codes", [])
    assert "insufficient_diagnostic_grounding" in validation.get("issue_codes", [])
    assert validation.get("review_required") is True
    result = (update.get("diagnostic_results") or [])[0]
    audit_ref = (result.get("audit_refs") or [None])[0]
    assert audit_ref
    event = session.get(OrchestrationAuditEvent, audit_ref)
    assert event is not None
    assert event.node_name == "diagnostic_item"
    audit_sources = event.source_revision_ids_json.get("ids") or []
    assert set(audit_sources) == set(revisions)
    assert "insufficient_diagnostic_grounding" in (event.issue_codes_json or [])
    from app.diagnostic_intelligence.integration.day7_diagnostic_context import (
        build_diagnostic_day7_payload,
    )

    _, visible_snippets = build_diagnostic_day7_payload(pack)
    assert len(visible_snippets) < len(revisions)
    session.close()
