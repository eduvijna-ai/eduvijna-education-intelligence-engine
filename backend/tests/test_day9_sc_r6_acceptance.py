"""Day 9 spec-closure repair round 6 (D9-SC-R6-01…02)."""

from __future__ import annotations

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
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService


def _r6_orphan_citation_request() -> DiagnosticAuthoringRequest:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    item = build_fixture_mcq_item(item_id="r6-orphan-cit").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    return DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=["[CIT-1]", "[CIT-X]"],
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-1]",
                source_revision_id=rev_a,
                snippet="approved",
            )
        ],
        trusted_citation_revision_map={"[CIT-1]": rev_a, "[CIT-X]": rev_a},
        bounded_day7_context=f"[CIT-1] (revision {rev_a})",
    )


def test_orphan_trusted_citation_label_rejected_by_preflight() -> None:
    request = _r6_orphan_citation_request()
    preflight = run_diagnostic_preflight(request)
    assert not preflight.allow_model_call
    assert "forged_evidence_ref" in preflight.issue_codes


def test_orphan_trusted_citation_label_rejected_by_direct_service() -> None:
    request = _r6_orphan_citation_request()
    item = request.item
    tags = build_fixture_tags(item)
    tags[0] = tags[0].model_copy(update={"evidence_refs": ["[CIT-X]"]})
    tags[2] = tags[2].model_copy(update={"evidence_refs": ["[CIT-1]"]})
    verdict = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.blocking
    assert verdict.status.value != "pass"
    assert "unbound_diagnostic_evidence" in verdict.issue_codes


def test_two_visible_citations_same_revision_pass() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    item = build_fixture_mcq_item(item_id="r6-dual-cit").model_copy(
        update={"source_revision_ids": [rev_a]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a],
        allowed_evidence_refs=["[CIT-1]", "[CIT-2]"],
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-1]",
                source_revision_id=rev_a,
                snippet="first excerpt",
            ),
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-2]",
                source_revision_id=rev_a,
                snippet="second excerpt",
            ),
        ],
        trusted_citation_revision_map={"[CIT-1]": rev_a, "[CIT-2]": rev_a},
        bounded_day7_context=(
            f"[CIT-1] (revision {rev_a})\nfirst excerpt\n"
            f"[CIT-2] (revision {rev_a})\nsecond excerpt"
        ),
    )
    tags = build_fixture_tags(item)
    tags[0] = tags[0].model_copy(update={"evidence_refs": ["[CIT-1]"]})
    tags[2] = tags[2].model_copy(update={"evidence_refs": ["[CIT-2]"]})
    verdict = DiagnosticIntelligenceService().validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value == "pass"


def test_visible_citation_with_wrong_trusted_revision_rejected() -> None:
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    rev_b = "00000000-0000-0000-0000-0000000000bb"
    item = build_fixture_mcq_item(item_id="r6-wrong-bound").model_copy(
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


def test_compact_x_multiplication_rejected_by_numeric_helpers() -> None:
    for text in ("11x2", "11X2", "11 x2", "11x 2", "11 x 2", "11 times 2"):
        assert has_unsupported_arithmetic_expression(text)
        assert not numeric_literal_matches_integer(text, 11)
    assert numeric_literal_matches_integer("11", 11)
    assert numeric_literal_matches_integer("11.0", 11)
    assert numeric_literal_matches_integer("11 off-by-one-low", 11)
    assert not has_unsupported_arithmetic_expression("13 successor")


def test_service_rejects_compact_x_multiplication_off_by_one_low() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="r6-11x2", wrong_a="11x2")
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
    tags[0].metadata_json["option_text"] = "11x2"
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value != "pass"
    assert (
        "signal_text_mismatch" in verdict.issue_codes
        or "plausibility_unverified" in verdict.issue_codes
    )
