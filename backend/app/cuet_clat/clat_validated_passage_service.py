"""F03-B: validated original synthetic CLAT passage examples (harness-only)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from app.cuet_clat.clat_independent_answer_check import independently_check_mcq
from app.cuet_clat.clat_passage_contracts import (
    _ALLOWED_OPTION_KEYS,
    CLAT_ORIGINAL_SOURCE_MODE,
    CLAT_PASSAGE_HARNESS_TOKEN,
    F03B_EXPECTED_ITEM_COUNT,
    F03B_EXPECTED_PASSAGE_COUNT,
    F03B_MIN_QUESTIONS_PER_SECTION,
    F03B_REQUIRED_SECTIONS,
    ClatAuthoredMcq,
    ClatIndependentCheckResult,
    ClatIndependentVerdict,
    ClatOriginalPassage,
    ClatPassageIssueCode,
    ClatValidatedExamplesResult,
    ClatValidatedQuestionRecord,
    authored_question_fingerprint,
    authored_to_practice_ref,
    global_passage_body_key,
    normalized_passage_body_key,
    validated_content_fingerprint,
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
    if not question.stem_text.strip():
        issue_codes.append(ClatPassageIssueCode.BLANK_OPTION)
        ok = False
    if set(question.options.keys()) != _ALLOWED_OPTION_KEYS:
        issue_codes.append(ClatPassageIssueCode.INVALID_OPTION_KEY)
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


def _strip_certification(records: list[ClatValidatedQuestionRecord]) -> None:
    for record in records:
        record.question.independently_validated = False
        record.question.solver_evidence_id = None
        record.independent = ClatIndependentCheckResult(
            verdict=ClatIndependentVerdict.FAIL,
            reason="Bundle certification withheld; see bundle issue_codes.",
        )
        record.certified_content_fingerprint = ""


def _section_certified_counts(records: list[ClatValidatedQuestionRecord]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        if record.question.independently_validated:
            counts[record.section_code] += 1
    return dict(counts)


def _validate_bundle_composition(
    passage_list: list[ClatOriginalPassage],
    records: list[ClatValidatedQuestionRecord],
    issue_codes: list[ClatPassageIssueCode],
) -> None:
    if len(passage_list) != F03B_EXPECTED_PASSAGE_COUNT:
        issue_codes.append(ClatPassageIssueCode.SECTION_SHORTAGE)
    sections_present = {p.section_code for p in passage_list}
    if sections_present != set(F03B_REQUIRED_SECTIONS):
        issue_codes.append(ClatPassageIssueCode.SECTION_SHORTAGE)

    certified = _section_certified_counts(records)
    for section in F03B_REQUIRED_SECTIONS:
        if certified.get(section, 0) < F03B_MIN_QUESTIONS_PER_SECTION:
            issue_codes.append(ClatPassageIssueCode.SECTION_SHORTAGE)

    certified_total = sum(1 for r in records if r.question.independently_validated)
    if certified_total != F03B_EXPECTED_ITEM_COUNT:
        issue_codes.append(ClatPassageIssueCode.SECTION_SHORTAGE)


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

    seen_passage_ids: set[str] = set()
    seen_body_keys: set[str] = set()
    seen_global_bodies: set[str] = set()
    seen_qids: set[str] = set()
    seen_stems: set[str] = set()

    for passage in passage_list:
        if not passage.passage_text.strip():
            issue_codes.append(ClatPassageIssueCode.BLANK_PASSAGE)
        if passage.source_mode != CLAT_ORIGINAL_SOURCE_MODE:
            issue_codes.append(ClatPassageIssueCode.INVALID_SOURCE_MODE)

        if passage.passage_id in seen_passage_ids:
            issue_codes.append(ClatPassageIssueCode.DUPLICATE_PASSAGE)
        seen_passage_ids.add(passage.passage_id)

        body_key = normalized_passage_body_key(passage.section_code, passage.passage_text)
        global_key = global_passage_body_key(passage.passage_text)
        if body_key in seen_body_keys or global_key in seen_global_bodies:
            issue_codes.append(ClatPassageIssueCode.DUPLICATE_PASSAGE)
        seen_body_keys.add(body_key)
        seen_global_bodies.add(global_key)

        expected_ids = [q.question_id for q in passage.questions]
        for qi, question in enumerate(passage.questions):
            if question.question_id != expected_ids[qi]:
                issue_codes.append(ClatPassageIssueCode.PASSAGE_MISMATCH)

        for question in passage.questions:
            stem_key = question.stem_text.strip().lower()
            if question.question_id in seen_qids:
                issue_codes.append(ClatPassageIssueCode.DUPLICATE_QUESTION)
            if stem_key in seen_stems:
                issue_codes.append(ClatPassageIssueCode.DUPLICATE_STEM)
            seen_qids.add(question.question_id)
            seen_stems.add(stem_key)

            if question.passage_id != passage.passage_id:
                issue_codes.append(ClatPassageIssueCode.WRONG_PASSAGE_ID)
            if question.section_code != passage.section_code:
                issue_codes.append(ClatPassageIssueCode.CROSS_SECTION)

            structure_ok = _validate_question_structure(question, issue_codes)

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

            if independent.anchor_quote and independent.anchor_quote not in passage.passage_text:
                issue_codes.append(ClatPassageIssueCode.INDEPENDENT_FAIL)

            authored_fp = authored_question_fingerprint(passage, question)
            certified_fp = validated_content_fingerprint(
                passage,
                question,
                derived_key=independent.derived_key,
                anchor_quote=independent.anchor_quote,
            )

            certified = (
                structure_ok
                and independent.verdict is ClatIndependentVerdict.PASS
                and independent.derived_key == question.author_key
                and independent.anchor_quote in passage.passage_text
            )

            practice = authored_to_practice_ref(question, fingerprint=authored_fp)
            practice.independently_validated = certified
            if certified:
                practice.fingerprint = certified_fp
                practice.solver_evidence_id = f"d13-clat-solver-{question.question_id}"

            records.append(
                ClatValidatedQuestionRecord(
                    question=practice,
                    passage_id=passage.passage_id,
                    section_code=passage.section_code,
                    independent=independent,
                    authored_content_fingerprint=authored_fp,
                    certified_content_fingerprint=certified_fp if certified else "",
                )
            )

    clusters = [build_passage_cluster(p) for p in passage_list]
    for passage, cluster in zip(passage_list, clusters, strict=True):
        expected_ids = [q.question_id for q in passage.questions]
        if cluster.question_ids != expected_ids or cluster.section_code != passage.section_code:
            issue_codes.append(ClatPassageIssueCode.PASSAGE_MISMATCH)

    _validate_bundle_composition(passage_list, records, issue_codes)

    issue_codes = _dedupe_issues(issue_codes)
    validated_count = sum(1 for r in records if r.question.independently_validated)

    verdict = PlanVerdict.PASS
    if issue_codes:
        verdict = PlanVerdict.FAIL
    elif validated_count < F03B_EXPECTED_ITEM_COUNT:
        verdict = PlanVerdict.SHORTAGE

    if verdict is not PlanVerdict.PASS:
        _strip_certification(records)
        validated_count = 0

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
        issue_codes=issue_codes,
        metadata_json={
            "validated_clat_original_passage_examples": verdict is PlanVerdict.PASS,
            "validated_independent_count": validated_count,
            "source_mode": CLAT_ORIGINAL_SOURCE_MODE,
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