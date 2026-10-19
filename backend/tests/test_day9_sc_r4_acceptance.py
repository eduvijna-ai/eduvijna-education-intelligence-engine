"""Day 9 spec-closure repair round 4 (D9-SC-R4-01…03)."""

from __future__ import annotations

import uuid

import pytest

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
    measure_diagnostic_evidence_payload_chars,
)
from app.diagnostic_intelligence.numeric_tokens import (
    has_unsupported_arithmetic_expression,
    numeric_literal_equals_correct_sum,
    numeric_literal_matches_integer,
)
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.knowledge_intelligence.contracts import (
    AppliedKnowledgeScope,
    KnowledgeContextPack,
    KnowledgeEvidenceItem,
)


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


def test_eight_distinct_revisions_preflight_not_unauthorized_on_truncation() -> None:
    revisions = [str(uuid.uuid4()) for _ in range(8)]
    pack = KnowledgeContextPack(
        query_id="multi-src",
        query_text="multi",
        retrieval_profile_version="ki-retrieval-v1",
        evidence=[
            _evidence_item(i + 1, revisions[i], "x" * 512) for i in range(8)
        ],
        citations=[],
        scope=AppliedKnowledgeScope(),
        warnings=[],
        bounded_text="",
    )
    bounded, snippets = build_diagnostic_day7_payload(pack)
    assert measure_diagnostic_evidence_payload_chars(
        DiagnosticAuthoringRequest(
            item=build_fixture_mcq_item().model_copy(
                update={"source_revision_ids": revisions}
            ),
            bounded_day7_context=bounded,
            day7_evidence_snippets=snippets,
            allowed_source_revision_ids=revisions,
            allowed_evidence_refs=[s.citation_label for s in snippets],
            trusted_citation_revision_map={
                s.citation_label: s.source_revision_id for s in snippets
            },
        )
    ) <= 4000
    request = DiagnosticAuthoringRequest(
        item=build_fixture_mcq_item().model_copy(update={"source_revision_ids": revisions}),
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=revisions,
        allowed_evidence_refs=[s.citation_label for s in snippets],
        bounded_day7_context=bounded,
        day7_evidence_snippets=snippets,
        trusted_citation_revision_map={
            s.citation_label: s.source_revision_id for s in snippets
        },
    )
    preflight = run_diagnostic_preflight(request)
    assert "unauthorized_source_revision" not in preflight.issue_codes
    assert preflight.status.value in {"pass", "review_required"}


def test_unbound_citation_in_allowed_refs_rejected() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    item = build_fixture_mcq_item(item_id="unbound-cit").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=["[CIT-A]", "[CIT-X]"],
        bounded_day7_context=f"[CIT-A] (revision {rev_a})",
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-A]",
                source_revision_id=rev_a,
                snippet="visible snippet",
            )
        ],
        trusted_citation_revision_map={"[CIT-A]": rev_a},
    )
    tags = build_fixture_tags(item)
    tags[0] = tags[0].model_copy(update={"evidence_refs": ["[CIT-X]"]})
    verdict = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value != "pass"
    assert "unbound_diagnostic_evidence" in verdict.issue_codes
    tags[0] = tags[0].model_copy(update={"evidence_refs": ["[CIT-A]"]})
    good = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert "unbound_diagnostic_evidence" not in good.issue_codes


@pytest.mark.parametrize(
    ("option_text", "code"),
    [
        ("7+5", "MATH.ADD.WHOLE.DOUBLE_OPERAND"),
        ("11 / 9", "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"),
        ("11 ^ 2", "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"),
        ("11e+2", "MATH.ADD.WHOLE.OFF_BY_ONE_LOW"),
    ],
)
def test_expression_ambiguity_never_passes(option_text: str, code: str) -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id=f"expr-{option_text}", wrong_a=option_text)
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
    tags[0] = tags[0].model_copy(
        update={"misconception_code": code, "evidence_refs": ["[CIT-1]"]}
    )
    tags[0].metadata_json["option_text"] = option_text
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value != "pass"


def test_numeric_helpers_reject_spaced_expressions() -> None:
    assert has_unsupported_arithmetic_expression("7+5")
    assert has_unsupported_arithmetic_expression("11 / 9")
    assert not numeric_literal_matches_integer("11 / 9", 11)
    assert not numeric_literal_matches_integer("7+5", 7)
    assert numeric_literal_equals_correct_sum("7+5", 12)


def test_double_operand_expression_is_second_correct() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="second-correct-expr", wrong_a="7+5")
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
    tags[0] = tags[0].model_copy(
        update={
            "misconception_code": "MATH.ADD.WHOLE.DOUBLE_OPERAND",
            "diagnostic_signal": "double",
        }
    )
    tags[0].metadata_json["option_text"] = "7+5"
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert "second_correct_distractor" in verdict.issue_codes
