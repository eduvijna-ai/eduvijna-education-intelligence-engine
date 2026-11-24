"""F03-B iteration 3: final adversarial and bundle-proof tests."""

from __future__ import annotations

import copy
import re

from app.cuet_clat.clat_independent_answer_check import (
    _parse_riverton_rules,
    independently_check_mcq,
)
from app.cuet_clat.clat_original_passages import (
    ENGLISH_PASSAGE,
    LEGAL_PASSAGE,
    LOGICAL_PASSAGE,
    load_original_synthetic_f03b_passages,
)
from app.cuet_clat.clat_passage_contracts import (
    CLAT_PASSAGE_HARNESS_TOKEN,
    STEM_ENGLISH_PLANNING,
    ClatIndependentVerdict,
    ClatPassageIssueCode,
    validated_content_fingerprint,
)
from app.cuet_clat.clat_validated_passage_service import (
    build_validated_clat_original_passage_examples,
    validate_clat_original_passage_bundle,
)
from app.cuet_clat.enums import PlanVerdict


def test_logical_fails_without_priya_membership_in_passage() -> None:
    logic = copy.deepcopy(LOGICAL_PASSAGE)
    logic.passage_text = logic.passage_text.replace("Priya is a member of the study group and ", "")
    q = logic.questions[0]
    result = independently_check_mcq(
        passage_text=logic.passage_text,
        section_code="logical_reasoning",
        question=q,
    )
    assert result.verdict is not ClatIndependentVerdict.PASS


def test_english_negated_planning_stem_not_pass() -> None:
    q = copy.deepcopy(ENGLISH_PASSAGE.questions[0])
    q.stem_text = "According to the passage, how long did volunteers not spend on planning?"
    result = independently_check_mcq(
        passage_text=ENGLISH_PASSAGE.passage_text,
        section_code="english",
        question=q,
    )
    assert result.verdict is not ClatIndependentVerdict.PASS


def test_legal_weekend_rule_blocks_weekday_violation_pass() -> None:
    legal = copy.deepcopy(LEGAL_PASSAGE)
    legal.passage_text = legal.passage_text.replace("on weekdays between", "on weekends between")
    q = legal.questions[0]
    result = independently_check_mcq(
        passage_text=legal.passage_text,
        section_code="legal_reasoning",
        question=q,
    )
    assert result.derived_key != q.author_key or result.verdict is not ClatIndependentVerdict.PASS


def test_legal_penalty_1500_option_does_not_match_500_rule() -> None:
    options = {
        "A": "Pay 1500 transit credits for Rule 7",
        "B": "The truck must pay 500 transit credits for a Rule 7 violation",
        "C": "No penalty",
        "D": "Unknown",
    }
    q = copy.deepcopy(LEGAL_PASSAGE.questions[0])
    q.options = options
    result = independently_check_mcq(
        passage_text=LEGAL_PASSAGE.passage_text,
        section_code="legal_reasoning",
        question=q,
    )
    assert result.derived_key == "B"
    rules = _parse_riverton_rules(LEGAL_PASSAGE.passage_text)
    assert rules is not None
    assert not re.search(r"(?<!\d)1500(?!\d)", options["B"])


def test_cross_section_duplicate_body_rejected() -> None:
    passages = list(load_original_synthetic_f03b_passages())
    twin = copy.deepcopy(ENGLISH_PASSAGE)
    twin.passage_id = "d13-clat-p-cross-section-dup"
    twin.section_code = "legal_reasoning"
    bundle = validate_clat_original_passage_bundle(
        passages + [twin],
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.FAIL
    assert ClatPassageIssueCode.DUPLICATE_PASSAGE in bundle.issue_codes


def test_failed_bundle_strips_independent_pass_indicators() -> None:
    passages = list(load_original_synthetic_f03b_passages())
    legal = copy.deepcopy(LEGAL_PASSAGE)
    legal.questions[0].author_key = "A"
    mutated = [p for p in passages if p.section_code != "legal_reasoning"] + [legal]
    bundle = validate_clat_original_passage_bundle(
        mutated,
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.FAIL
    assert all(not r.question.independently_validated for r in bundle.questions)
    assert all(
        r.independent.verdict is not ClatIndependentVerdict.PASS for r in bundle.questions
    )
    assert all(not r.certified_content_fingerprint for r in bundle.questions)


def test_certified_practice_ref_uses_post_proof_fingerprint() -> None:
    bundle = build_validated_clat_original_passage_examples(
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.PASS
    record = bundle.questions[0]
    assert record.question.fingerprint == record.certified_content_fingerprint
    assert record.question.fingerprint != record.authored_content_fingerprint or (
        validated_content_fingerprint(
            bundle.passages[0],
            bundle.passages[0].questions[0],
            derived_key=record.independent.derived_key,
            anchor_quote=record.independent.anchor_quote,
        )
        == record.certified_content_fingerprint
    )


def test_english_exact_stem_baseline_still_passes() -> None:
    q = ENGLISH_PASSAGE.questions[0]
    assert q.stem_text == STEM_ENGLISH_PLANNING
    result = independently_check_mcq(
        passage_text=ENGLISH_PASSAGE.passage_text,
        section_code="english",
        question=q,
    )
    assert result.verdict is ClatIndependentVerdict.PASS