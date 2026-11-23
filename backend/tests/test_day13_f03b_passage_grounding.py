"""F03-B iteration 1: CLAT original passage-grounded MCQ foundation."""

from __future__ import annotations

import copy

from app.cuet_clat.clat_independent_answer_check import independently_check_mcq
from app.cuet_clat.clat_original_passages import (
    ENGLISH_PASSAGE,
    LEGAL_PASSAGE,
    QUANT_PASSAGE,
    load_official_f03b_passages,
)
from app.cuet_clat.clat_passage_contracts import (
    CLAT_PASSAGE_HARNESS_TOKEN,
    ClatPassageIssueCode,
    authored_question_fingerprint,
    normalized_passage_body_key,
    validated_content_fingerprint,
)
from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.clat_validated_passage_service import (
    build_validated_clat_original_passage_examples,
    validate_clat_original_passage_bundle,
    validate_with_substituted_passage,
)
from app.cuet_clat.constants import (
    CLAT_MARK_BLANK,
    CLAT_MARK_CORRECT,
    CLAT_MARK_INCORRECT,
    CLAT_PACK_CODE,
)
from app.cuet_clat.contracts import ClatPaperPlanRequest
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, PlanVerdict


def test_harness_requires_explicit_authorization() -> None:
    closed = build_validated_clat_original_passage_examples(harness_authorized=False)
    assert closed.verdict is PlanVerdict.NOT_READY
    assert ClatPassageIssueCode.HARNESS_UNAUTHORIZED in closed.issue_codes

    wrong_token = build_validated_clat_original_passage_examples(
        harness_authorized=True,
        trusted_harness_token="wrong",
    )
    assert wrong_token.verdict is PlanVerdict.FAIL


def test_validated_original_passage_examples_pass_twelve_mcq() -> None:
    bundle = build_validated_clat_original_passage_examples(
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.PASS
    assert bundle.passage_count == 4
    assert bundle.item_count == 12
    assert bundle.official_source_verified is False
    assert bundle.metadata_json.get("current_affairs_gk") == "source_pending_not_included"
    assert bundle.metadata_json.get("validated_clat_original_passage_examples") is True

    sections = {r.section_code for r in bundle.questions}
    assert sections == {
        "english",
        "legal_reasoning",
        "logical_reasoning",
        "quantitative_techniques",
    }

    for record in bundle.questions:
        q = record.question
        assert q.stem_text and q.options
        assert len(q.options) == 4
        assert q.marks_if_correct == CLAT_MARK_CORRECT
        assert q.marks_if_incorrect == CLAT_MARK_INCORRECT
        assert q.independently_validated
        assert record.independent.anchor_quote
        assert record.independent.proof_steps
        assert record.passage_id == q.passage_id


def test_structural_120_demo_remains_demonstration_only() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2027",
        )
    )
    assert plan.verdict is PlanVerdict.PASS
    assert plan.total_questions == 120
    assert plan.metadata_json.get("demonstration_only") is True
    assert all(q.correct_key == "B" and not q.stem_text for q in plan.questions)

    bundle = build_validated_clat_original_passage_examples(
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.item_count != 120
    assert bundle.demonstration_only is False


def test_wrong_passage_text_fails_independent_check() -> None:
    passages = list(load_official_f03b_passages())
    bundle = validate_with_substituted_passage(
        passages,
        target_question_id="d13-clat-q-english-001",
        substitute_passage=QUANT_PASSAGE,
    )
    assert bundle.verdict is PlanVerdict.FAIL
    assert ClatPassageIssueCode.INDEPENDENT_FAIL in bundle.issue_codes or (
        ClatPassageIssueCode.UNSUPPORTED_INFERENCE in bundle.issue_codes
    )


def test_answer_key_tamper_detected() -> None:
    passages = list(load_official_f03b_passages())
    legal = copy.deepcopy(LEGAL_PASSAGE)
    legal.questions[0].author_key = "A"
    mutated = [p for p in passages if p.section_code != "legal_reasoning"] + [legal]
    bundle = validate_clat_original_passage_bundle(
        mutated,
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.FAIL
    assert ClatPassageIssueCode.ANSWER_KEY_TAMPER in bundle.issue_codes


def test_duplicate_option_text_fails() -> None:
    passages = list(load_official_f03b_passages())
    english = copy.deepcopy(ENGLISH_PASSAGE)
    english.questions[0].options["D"] = english.questions[0].options["B"]
    mutated = [p for p in passages if p.section_code != "english"] + [english]
    bundle = validate_clat_original_passage_bundle(
        mutated,
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.FAIL
    assert ClatPassageIssueCode.DUPLICATE_OPTION in bundle.issue_codes


def test_changed_quant_table_fails_recompute() -> None:
    passages = list(load_official_f03b_passages())
    quant = copy.deepcopy(QUANT_PASSAGE)
    quant.passage_text = quant.passage_text.replace("| Pens | 12 |", "| Pens | 10 |")
    mutated = [p for p in passages if p.section_code != "quantitative_techniques"] + [quant]
    bundle = validate_clat_original_passage_bundle(
        mutated,
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.FAIL


def test_content_fingerprint_changes_on_tamper() -> None:
    baseline = authored_question_fingerprint(ENGLISH_PASSAGE, ENGLISH_PASSAGE.questions[0])
    tampered = copy.deepcopy(ENGLISH_PASSAGE.questions[0])
    tampered.stem_text += " (edited)"
    assert authored_question_fingerprint(ENGLISH_PASSAGE, tampered) != baseline

    alt_passage = copy.deepcopy(ENGLISH_PASSAGE)
    alt_passage.passage_text += " Extra sentence."
    assert authored_question_fingerprint(alt_passage, ENGLISH_PASSAGE.questions[0]) != baseline


def test_english_off_topic_stem_no_pass() -> None:
    q = copy.deepcopy(ENGLISH_PASSAGE.questions[0])
    q.stem_text = "What colour is the library roof?"
    result = independently_check_mcq(
        passage_text=ENGLISH_PASSAGE.passage_text,
        section_code="english",
        question=q,
    )
    assert result.verdict.value != "pass"


def test_legal_rule_change_invalidates_answer() -> None:
    legal = copy.deepcopy(LEGAL_PASSAGE)
    legal.passage_text = legal.passage_text.replace("three tonnes", "five tonnes")
    q = legal.questions[0]
    result = independently_check_mcq(
        passage_text=legal.passage_text,
        section_code="legal_reasoning",
        question=q,
    )
    assert result.derived_key != q.author_key or result.verdict.value != "pass"


def test_logical_wrong_passage_no_pass() -> None:
    q = copy.deepcopy(ENGLISH_PASSAGE).questions[0]
    q.question_id = "d13-clat-q-logical-adversarial"
    q.section_code = "logical_reasoning"
    q.stem_text = (
        "Which conclusion necessarily follows from Premises 1 and 2 alone?"
    )
    q.options = {
        "A": "Priya passed the mock exam",
        "B": "Priya failed",
        "C": "Unknown",
        "D": "All failed",
    }
    q.author_key = "A"
    result = independently_check_mcq(
        passage_text=ENGLISH_PASSAGE.passage_text,
        section_code="logical_reasoning",
        question=q,
    )
    assert result.verdict.value != "pass"


def test_invalid_bundle_has_zero_certified() -> None:
    passages = list(load_official_f03b_passages())
    legal = copy.deepcopy(LEGAL_PASSAGE)
    legal.questions[0].author_key = "A"
    mutated = [p for p in passages if p.section_code != "legal_reasoning"] + [legal]
    bundle = validate_clat_original_passage_bundle(
        mutated,
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.FAIL
    assert sum(1 for r in bundle.questions if r.question.independently_validated) == 0


def test_duplicate_passage_body_detected() -> None:
    passages = list(load_official_f03b_passages())
    twin = copy.deepcopy(ENGLISH_PASSAGE)
    twin.passage_id = "d13-clat-p-english-dup"
    bundle = validate_clat_original_passage_bundle(
        passages + [twin],
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    assert bundle.verdict is PlanVerdict.FAIL
    assert ClatPassageIssueCode.DUPLICATE_PASSAGE in bundle.issue_codes
    assert normalized_passage_body_key(twin.section_code, twin.passage_text) == (
        normalized_passage_body_key(ENGLISH_PASSAGE.section_code, ENGLISH_PASSAGE.passage_text)
    )


def test_validated_fingerprint_includes_proof_anchor() -> None:
    q = ENGLISH_PASSAGE.questions[0]
    ind = independently_check_mcq(
        passage_text=ENGLISH_PASSAGE.passage_text,
        section_code="english",
        question=q,
    )
    fp1 = validated_content_fingerprint(
        ENGLISH_PASSAGE,
        q,
        derived_key=ind.derived_key,
        anchor_quote=ind.anchor_quote,
    )
    fp2 = validated_content_fingerprint(
        ENGLISH_PASSAGE,
        q,
        derived_key="Z",
        anchor_quote=ind.anchor_quote,
    )
    assert fp1 != fp2


def test_clat_closing_marks_profile_present() -> None:
    bundle = build_validated_clat_original_passage_examples(
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )
    scoring = bundle.metadata_json.get("scoring_profile")
    assert isinstance(scoring, dict)
    assert scoring["correct"] == CLAT_MARK_CORRECT
    assert scoring["incorrect"] == CLAT_MARK_INCORRECT
    assert scoring["blank"] == CLAT_MARK_BLANK