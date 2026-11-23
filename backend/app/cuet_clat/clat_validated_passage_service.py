"""F03-B: validated original synthetic CLAT passage examples (harness-only)."""

from __future__ import annotations

from collections.abc import Iterable

from app.cuet_clat.clat_independent_answer_check import independently_check_mcq
from app.cuet_clat.clat_passage_contracts import (
    CLAT_PASSAGE_HARNESS_TOKEN,
    ClatAuthoredMcq,
    ClatIndependentVerdict,
    ClatOriginalPassage,
    ClatPassageIssueCode,
    ClatValidatedExamplesResult,
    ClatValidatedQuestionRecord,
    authored_to_practice_ref,
    question_content_fingerprint,
)
from app.cuet_clat.clat_question_author import (
    build_passage_cluster,
    load_authored_passage_fixtures,
)
from app.cuet_clat.constants import CLAT_MARK_BLANK, CLAT_MARK_CORRECT, CLAT_MARK_INCORRECT
from app.cuet_clat.enums import PlanVerdict


def _validate_question_structure(
    question: ClatAuthoredMcq,
    issue_codes: list[ClatPassageIssueCode],
) -> bool:
    ok = True
    if len(question.options) != 4:
        issue_codes.append(ClatPassageIssueCode.BLANK_OPTION)
        ok = False
    texts = [t.strip() for t in question.options.values()]
    if any(not t for t in texts):
        issue_codes.append(ClatPassageIssueCode.BLANK_OPTION)
        ok = False
    if len(set(texts)) != 4:
        issue_codes.append(ClatPassageIssueCode.DUPLICATE_OPTION)
        ok = False
    if question.author_key not in question.options:
        issue_codes.append(ClatPassageIssueCode.ANSWER_KEY_TAMPER)
        ok = False
    return ok


def validate_clat_original_passage_bundle(
    passages: Iterable[ClatOriginalPassage],
    *,
    harness_authorized: bool,
    trusted_harness_token: str | None = None,
) -> ClatValidatedExamplesResult:
    """Validate authored passages + independent checks; not a 120-question paper path."""

    if not harness_authorized:
        return ClatValidatedExamplesResult(
            verdict=PlanVerdict.NOT_READY,
            harness_authorized=False,
            issue_codes=[ClatPassageIssueCode.HARNESS_UNAUTHORIZED],
            metadata_json={
                "validated_clat_original_passage_examples": False,
                "current_affairs_gk": "source_pending",
            },
        )

    if trusted_harness_token != CLAT_PASSAGE_HARNESS_TOKEN:
        return ClatValidatedExamplesResult(
            verdict=PlanVerdict.FAIL,
            harness_authorized=False,
            issue_codes=[ClatPassageIssueCode.HARNESS_UNAUTHORIZED],
            metadata_json={"validated_clat_original_passage_examples": False},
        )

    passage_list = list(passages)
    issue_codes: list[ClatPassageIssueCode] = []
    records: list[ClatValidatedQuestionRecord] = []
    clusters = [build_passage_cluster(p) for p in passage_list]

    passage_texts = {p.passage_fingerprint() for p in passage_list}
    if len(passage_texts) != len(passage_list):
        issue_codes.append(ClatPassageIssueCode.DUPLICATE_PASSAGE)

    seen_qids: set[str] = set()
    for passage in passage_list:
        for question in passage.questions:
            if question.question_id in seen_qids:
                issue_codes.append(ClatPassageIssueCode.DUPLICATE_QUESTION)
            seen_qids.add(question.question_id)

            if question.passage_id != passage.passage_id:
                issue_codes.append(ClatPassageIssueCode.WRONG_PASSAGE_ID)
            if question.section_code != passage.section_code:
                issue_codes.append(ClatPassageIssueCode.CROSS_SECTION)

            if not _validate_question_structure(question, issue_codes):
                continue

            independent = independently_check_mcq(
                passage_text=passage.passage_text,
                section_code=passage.section_code,
                question=question,
            )

            if independent.verdict is ClatIndependentVerdict.FAIL:
                issue_codes.append(ClatPassageIssueCode.INDEPENDENT_FAIL)
            elif independent.verdict is ClatIndependentVerdict.REVIEW_REQUIRED:
                issue_codes.append(ClatPassageIssueCode.UNSUPPORTED_INFERENCE)
            elif (
                independent.derived_key
                and independent.derived_key != question.author_key
            ):
                issue_codes.append(ClatPassageIssueCode.ANSWER_KEY_TAMPER)

            practice = authored_to_practice_ref(question)
            validated = (
                independent.verdict is ClatIndependentVerdict.PASS
                and independent.derived_key == question.author_key
            )
            practice.independently_validated = validated
            if validated:
                practice.solver_evidence_id = f"d13-clat-solver-{question.question_id}"

            records.append(
                ClatValidatedQuestionRecord(
                    question=practice,
                    passage_id=passage.passage_id,
                    section_code=passage.section_code,
                    independent=independent,
                    content_fingerprint=question_content_fingerprint(question),
                )
            )

    validated_count = sum(1 for r in records if r.question.independently_validated)
    verdict = PlanVerdict.PASS
    if issue_codes:
        verdict = PlanVerdict.FAIL
    elif validated_count < 12:
        verdict = PlanVerdict.SHORTAGE

    return ClatValidatedExamplesResult(
        verdict=verdict,
        harness_authorized=True,
        official_source_verified=False,
        demonstration_only=False,
        item_count=len(records),
        passage_count=len(passage_list),
        passages=passage_list,
        passage_clusters=clusters,
        questions=records,
        issue_codes=_dedupe_issues(issue_codes),
        metadata_json={
            "validated_clat_original_passage_examples": verdict is PlanVerdict.PASS,
            "validated_independent_count": validated_count,
            "source_mode": "eduvijna_original_synthetic_test_only",
            "current_affairs_gk": "source_pending_not_included",
            "scoring_profile": {
                "correct": CLAT_MARK_CORRECT,
                "incorrect": CLAT_MARK_INCORRECT,
                "blank": CLAT_MARK_BLANK,
            },
            "harness_token_required": CLAT_PASSAGE_HARNESS_TOKEN,
            "structural_120_demo_separate": True,
        },
    )


def build_validated_clat_original_passage_examples(
    *,
    harness_authorized: bool,
    trusted_harness_token: str | None = None,
) -> ClatValidatedExamplesResult:
    return validate_clat_original_passage_bundle(
        load_authored_passage_fixtures(),
        harness_authorized=harness_authorized,
        trusted_harness_token=trusted_harness_token,
    )


def validate_with_substituted_passage(
    passages: list[ClatOriginalPassage],
    *,
    target_question_id: str,
    substitute_passage: ClatOriginalPassage,
) -> ClatValidatedExamplesResult:
    """Adversarial helper: bind a question to the wrong passage text."""

    mutated: list[ClatOriginalPassage] = []
    for passage in passages:
        if any(q.question_id == target_question_id for q in passage.questions):
            wrong = passage.model_copy(deep=True)
            wrong.passage_text = substitute_passage.passage_text
            mutated.append(wrong)
        else:
            mutated.append(passage)
    return validate_clat_original_passage_bundle(
        mutated,
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )


def _dedupe_issues(issues: list[ClatPassageIssueCode]) -> list[ClatPassageIssueCode]:
    seen: set[ClatPassageIssueCode] = set()
    ordered: list[ClatPassageIssueCode] = []
    for code in issues:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered