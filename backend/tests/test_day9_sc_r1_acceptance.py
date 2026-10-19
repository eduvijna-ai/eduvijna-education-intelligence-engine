"""Day 9 spec-closure repair round 1 (D9-SC-R1-01…06)."""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates
from app.diagnostic_intelligence.contracts import (
    Day7DiagnosticEvidenceSnippet,
    DiagnosticAuthoringRequest,
    MisconceptionDefinition,
    MisconceptionStatus,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus
from app.diagnostic_intelligence.fixtures import (
    build_fixture_mcq_item,
    build_fixture_result,
    build_fixture_tags,
)
from app.diagnostic_intelligence.preflight import run_diagnostic_preflight
from app.diagnostic_intelligence.service import DiagnosticIntelligenceService
from app.diagnostic_intelligence.validators.plausibility import validate_plausibility


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def _source_backed_request(
    *,
    metadata: dict,
    evidence_refs_empty: bool = True,
) -> tuple[DiagnosticAuthoringRequest, list]:
    item = build_fixture_mcq_item(item_id="sc-r1-source").model_copy(
        update={
            "metadata_json": metadata,
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
        bounded_day7_context="[CIT-1] (revision 00000000-0000-0000-0000-000000000099)",
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-1]",
                source_revision_id="00000000-0000-0000-0000-000000000099",
                snippet="approved fixture snippet",
            )
        ],
    )
    tags = build_fixture_tags(item)
    if evidence_refs_empty:
        tags[0] = tags[0].model_copy(update={"evidence_refs": []})
    return request, tags


def test_source_backed_rejects_empty_refs_despite_synthetic_metadata() -> None:
    service = DiagnosticIntelligenceService()
    for metadata in ({}, {"synthetic_fixture": True}):
        request, tags = _source_backed_request(metadata=metadata)
        verdict = service.validate_result(
            request,
            build_fixture_result(request.item, tags),
            candidate_codes={
                c.misconception_code for c in resolve_misconception_candidates(request)
            },
        )
        assert verdict.status.value != "pass"
        assert "missing_diagnostic_evidence" in verdict.issue_codes


def test_source_free_fixture_passes_without_refs() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="sc-r1-free").model_copy(
        update={"source_revision_ids": [], "metadata_json": {"synthetic_fixture": True}}
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
    tags[0] = tags[0].model_copy(update={"evidence_refs": []})
    verdict = service.validate_result(
        request,
        build_fixture_result(item, tags, source_revision_ids=[]),
        candidate_codes={c.misconception_code for c in resolve_misconception_candidates(request)},
    )
    assert verdict.status.value == "pass"


def test_preflight_blocks_missing_authorized_revisions_before_model() -> None:
    item = build_fixture_mcq_item().model_copy(
        update={"source_revision_ids": ["rev-canonical-only"]}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[],
        allowed_evidence_refs=["[CIT-1]"],
        bounded_day7_context="",
    )
    preflight = run_diagnostic_preflight(request)
    assert not preflight.allow_model_call
    assert "source_authorization_unresolved" in preflight.issue_codes


def test_taxonomy_authoritative_revision_must_match() -> None:
    service = DiagnosticIntelligenceService()
    rev_a = "00000000-0000-0000-0000-0000000000aa"
    rev_b = "00000000-0000-0000-0000-0000000000bb"
    item = build_fixture_mcq_item(item_id="tax-ground").model_copy(
        update={"source_revision_ids": [rev_a, rev_b], "metadata_json": {}}
    )
    request = DiagnosticAuthoringRequest(
        item=item,
        subject_code="mathematics",
        grade_year_code="grade-8",
        topic_codes=["whole-numbers"],
        concept_codes=["addition-whole"],
        allowed_source_revision_ids=[rev_a, rev_b],
        allowed_evidence_refs=["[CIT-A]", "[CIT-B]"],
        bounded_day7_context="index",
        day7_evidence_snippets=[
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-A]", source_revision_id=rev_a, snippet="a"
            ),
            Day7DiagnosticEvidenceSnippet(
                citation_label="[CIT-B]", source_revision_id=rev_b, snippet="b"
            ),
        ],
    )
    tags = build_fixture_tags(item)
    tags[0] = tags[0].model_copy(update={"evidence_refs": ["[CIT-B]"]})
    fake_def = MisconceptionDefinition(
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        version="v1",
        title="t",
        description="d",
        domain="math",
        error_pattern="p",
        diagnostic_signal="s",
        evidence_source_revision_ids=[rev_a],
        status=MisconceptionStatus.ACTIVE,
    )
    with patch(
        "app.diagnostic_intelligence.validators.evidence_ref.resolve_misconception",
        return_value=fake_def,
    ):
        bad = service.validate_result(
            request,
            build_fixture_result(item, tags),
            candidate_codes={"MATH.ADD.WHOLE.OFF_BY_ONE_LOW"},
        )
    assert "taxonomy_evidence_ungrounded" in bad.issue_codes
    tags[0] = tags[0].model_copy(update={"evidence_refs": ["[CIT-A]"]})
    with patch(
        "app.diagnostic_intelligence.validators.evidence_ref.resolve_misconception",
        return_value=fake_def,
    ):
        good = service.validate_result(
            request,
            build_fixture_result(item, tags),
            candidate_codes={"MATH.ADD.WHOLE.OFF_BY_ONE_LOW"},
        )
    assert "taxonomy_evidence_ungrounded" not in good.issue_codes


def test_redundant_item_marks_wrong_options_not_all_pass() -> None:
    service = DiagnosticIntelligenceService()
    item = build_fixture_mcq_item(item_id="redundant-verdict", wrong_a="11", wrong_b="11.0")
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
    assert verdict.status == DiagnosticValidationStatus.REPAIR or verdict.repairable
    wrong_statuses = [
        entry.status
        for entry in verdict.items
        if entry.option_key in {"A", "C"}
    ]
    assert all(s.value != "pass" for s in wrong_statuses)
    enriched = service.attach_validation_status(result, verdict)
    assert all(
        tag.validation_status.value != "pass"
        for tag in enriched.option_tags
        if tag.option_key in {"A", "C"}
    )
    assert result.coverage_summary is not None
    assert not result.coverage_summary.coverage_complete


def test_plausibility_word_boundary_and_unsupported_stem() -> None:
    tag = OptionDiagnosticTag(
        item_id="p",
        option_key="A",
        is_correct=False,
        misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
    )
    stem = "Synthetic fixture: What is 7 + 5?"
    assert (
        validate_plausibility(
            tag, "111", stem_text=stem, taxonomy_version=DEFAULT_TAXONOMY_VERSION
        )
        == ["plausibility_unverified"]
    )
    assert validate_plausibility(
        tag,
        "11",
        stem_text="Synthetic number-sense: choose the best statement.",
        taxonomy_version=DEFAULT_TAXONOMY_VERSION,
    ) == ["plausibility_unverified"]
