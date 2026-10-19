"""Day 9 spec-closure repair round 3 (D9-SC-R3-01…04)."""

from __future__ import annotations

import uuid

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
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
)
from app.diagnostic_intelligence.integration.day7_diagnostic_context import (
    build_diagnostic_day7_payload,
    measure_composed_evidence_chars,
    measure_diagnostic_evidence_payload_chars,
)
from app.diagnostic_intelligence.numeric_tokens import numeric_literal_matches_integer
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.knowledge_intelligence.contracts import (
    AppliedKnowledgeScope,
    KnowledgeContextPack,
    KnowledgeEvidenceItem,
)
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


def test_pack_builder_respects_shared_aggregate_budget() -> None:
    revision = "00000000-0000-0000-0000-000000000036"
    pack = KnowledgeContextPack(
        query_id="pack-budget",
        query_text="budget probe",
        retrieval_profile_version="ki-retrieval-v1",
        evidence=[_evidence_item(i, revision, "x" * 512) for i in range(1, 9)],
        citations=[],
        scope=AppliedKnowledgeScope(),
        warnings=[],
        bounded_text="",
    )
    bounded, snippets = build_diagnostic_day7_payload(pack)
    request = DiagnosticAuthoringRequest(
        item=build_fixture_mcq_item().model_copy(update={"source_revision_ids": [revision]}),
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[revision],
        allowed_evidence_refs=[s.citation_label for s in snippets],
        bounded_day7_context=bounded,
        day7_evidence_snippets=snippets,
        trusted_citation_revision_map={
            s.citation_label: s.source_revision_id for s in snippets
        },
    )
    assert measure_diagnostic_evidence_payload_chars(request) <= 4000
    assert measure_composed_evidence_chars(bounded, snippets) <= 4000
    assert snippets


def test_numeric_parser_rejects_fraction_and_scientific() -> None:
    assert not numeric_literal_matches_integer("11/9", 11)
    assert not numeric_literal_matches_integer("11e2", 11)
    assert not numeric_literal_matches_integer("12/2", 12)
    assert numeric_literal_matches_integer("11", 11)
    assert numeric_literal_matches_integer("11.0", 11)


def test_service_rejects_11_slash_9_off_by_one_tag() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="frac-signal", wrong_a="11/9")
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
    tags[0].metadata_json["option_text"] = "11/9"
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value != "pass"
    assert "signal_text_mismatch" in verdict.issue_codes


def test_citation_revision_mismatch_rejected_at_preflight() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    rev_b = "00000000-0000-0000-0000-0000000000bb"
    item = build_fixture_mcq_item(item_id="cit-mismatch").model_copy(
        update={"source_revision_ids": [rev_a, rev_b]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a, rev_b],
        allowed_evidence_refs=["[CIT-A]", "[CIT-B]"],
        bounded_day7_context=f"[CIT-B] (revision {rev_b})",
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-B]",
                source_revision_id=rev_a,
                snippet="wrongly attributed",
            )
        ],
        trusted_citation_revision_map={"[CIT-A]": rev_a, "[CIT-B]": rev_b},
    )
    preflight = run_diagnostic_preflight(request)
    assert not preflight.allow_model_call
    assert "forged_evidence_ref" in preflight.issue_codes


def test_direct_overbudget_request_still_fails_closed() -> None:
    rev = str(uuid.uuid4())
    with pytest.raises(ValidationError, match="diagnostic_evidence_budget_exceeded"):
        DiagnosticAuthoringRequest(
            item=build_fixture_mcq_item().model_copy(update={"source_revision_ids": [rev]}),
            subject_code="mathematics",
            grade_year_code="grade-8",
            topic_codes=["whole-numbers"],
            concept_codes=["addition-whole"],
            allowed_source_revision_ids=[rev],
            allowed_evidence_refs=["[CIT-A]"],
            bounded_day7_context="x" * 4000,
            day7_evidence_snippets=[
                Day7DiagnosticEvidenceSnippet(
                    citation_label="[CIT-A]",
                    source_revision_id=rev,
                    snippet="y" * 400,
                )
            ],
            trusted_citation_revision_map={"[CIT-A]": rev},
        )


def test_strict_output_failure_preserves_gateway_usage() -> None:
    session = _session()
    ctx, service = build_day8_test_service(session)
    result = service.run(
        build_diagnostic_orchestration_request(
            ctx,
            diagnostic_scenario="diagnostic_duplicate_option_keys",
            idempotency_key="sc-r3-dup-option-keys",
            max_repairs=0,
        )
    )
    assert result.status == OrchestrationRunStatus.FAILED
    usage = result.gateway_usage or {}
    by_role = usage.get("model_calls_by_role") or {}
    assert int(by_role.get("diagnostic", 0)) >= 1
    counts = (usage.get("token_usage_counts_by_role") or {}).get("diagnostic") or {}
    assert int(counts.get("reported", 0)) + int(counts.get("unknown", 0)) >= 1
    session.close()
