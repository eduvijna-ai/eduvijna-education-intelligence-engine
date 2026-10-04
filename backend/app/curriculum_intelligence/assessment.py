"""Conservative structured extraction of explicit sample-paper instructions.

Unparsed sections and arithmetic ambiguities remain review-required. We do not
infer exam blueprints or generate questions on Day 4.
"""

from __future__ import annotations

import re

from app.schemas.assessment_pattern import (
    AssessmentPattern,
    AssessmentQuestionCategory,
    AssessmentSection,
)


def _category(text: str) -> str:
    lowered = text.casefold()
    if "mcq" in lowered or "multiple choice" in lowered:
        return "multiple_choice"
    if "case" in lowered:
        return "case_study"
    if "very short" in lowered or "vsa" in lowered:
        return "very_short_answer"
    if "short" in lowered:
        return "short_answer"
    if "long" in lowered:
        return "long_answer"
    return "unspecified_response"


def extract_assessment_pattern(text: str, *, source_locator: str) -> AssessmentPattern:
    normalized = re.sub(r"\s+", " ", text)
    marks = re.search(r"(?:maximum|max\.?)[ ]*marks[ :.-]*(\d+)", normalized, re.I)
    duration = re.search(
        r"(?:time allowed|duration|time)[ :.-]*(\d+(?:\.\d+)?)\s*(hours?|minutes?)",
        normalized,
        re.I,
    )
    questions = re.search(
        r"(?:contains|comprises|has|there are)\s+(\d+)\s+questions", normalized, re.I
    )
    sections: list[AssessmentSection] = []
    unresolved: list[str] = []
    # Printed section summaries are more reliable than prose counting. Their
    # arithmetic is validated below; no hard-coded board-specific blueprint.
    summary_pattern = re.compile(
        r"SECTION\s*[-–—]?\s*([A-Z])\s*\((\d+)\s*[x×]\s*(\d+)\s*=\s*(\d+)\)",
        re.I,
    )
    number_words = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
        "sixteen": "16",
        "eighteen": "18",
        "twenty": "20",
    }
    counts_text = re.sub(
        r"\b(" + "|".join(number_words) + r")\b",
        lambda match: number_words[match.group(0).lower()],
        normalized,
        flags=re.I,
    )
    for match in summary_pattern.finditer(normalized):
        code, count, per_question, section_total = match.groups()
        count_int, marks_int = int(count), int(per_question)
        if int(section_total) != count_int * marks_int:
            unresolved.append(f"Section {code} printed arithmetic is inconsistent")
            continue
        locator = f"{source_locator} > Section {code.upper()} summary"
        fragments = re.findall(
            rf"Section\s+{code}\b(.*?)(?=Section\s+[A-Z]\b|$)", counts_text, re.I
        )
        kind = next(
            (
                fragment
                for fragment in fragments
                if re.search(r"contains|question number", fragment, re.I)
            ),
            "",
        )
        category = _category(kind)
        categories: list[AssessmentQuestionCategory] = []
        if category == "multiple_choice":
            range_match = re.search(
                r"(?:number|numbers)\s+(\d+)\s+to\s+(\d+)\s+are\s+Multiple", kind, re.I
            )
            count_match = re.search(r"(\d+)\s+MCQ", kind, re.I)
            mcq_count = (
                int(range_match.group(2)) - int(range_match.group(1)) + 1
                if range_match
                else int(count_match.group(1))
                if count_match
                else None
            )
            if mcq_count is not None and "assertion" in kind.lower():
                categories = [
                    AssessmentQuestionCategory(
                        code="multiple_choice",
                        question_count=mcq_count,
                        marks_per_question=marks_int,
                        source_locator=locator,
                    ),
                    AssessmentQuestionCategory(
                        code="assertion_reason",
                        question_count=count_int - mcq_count,
                        marks_per_question=marks_int,
                        source_locator=locator,
                    ),
                ]
        if not categories:
            categories = [
                AssessmentQuestionCategory(
                    code=category,
                    question_count=count_int,
                    marks_per_question=marks_int,
                    source_locator=locator,
                )
            ]
        sections.append(
            AssessmentSection(
                code=code.upper(),
                title=f"Section {code.upper()}",
                question_count=count_int,
                maximum_marks=int(section_total),
                source_locator=locator,
                categories=categories,
            )
        )
    # Generic count-based instructions are also accepted when explicit.
    prose = re.compile(
        r"Section\s*([A-Z])\s*(?:contains|comprises|has|consists of)\s*"
        r"(\d+)\s*([^.;]{0,140}?)\s*(?:carrying|of|with)\s*"
        r"(\d+)\s*marks?\s*(?:each|per question)",
        re.I,
    )
    for match in prose.finditer(counts_text):
        code, count, kind, per_question = match.groups()
        count_int, marks_int = int(count), int(per_question)
        existing = next((section for section in sections if section.code == code.upper()), None)
        if existing is not None:
            if (
                existing.question_count != count_int
                or existing.maximum_marks != count_int * marks_int
            ):
                unresolved.append(f"Section {code} prose and printed summary disagree")
            continue
        locator = f"{source_locator} > instructions > Section {code.upper()}"
        sections.append(
            AssessmentSection(
                code=code.upper(),
                title=f"Section {code.upper()}",
                question_count=count_int,
                maximum_marks=count_int * marks_int,
                source_locator=locator,
                categories=[
                    AssessmentQuestionCategory(
                        code=_category(kind),
                        question_count=count_int,
                        marks_per_question=marks_int,
                        source_locator=locator,
                    )
                ],
            )
        )
    total_marks = float(marks.group(1)) if marks else None
    total_questions = int(questions.group(1)) if questions else None
    duration_minutes = None
    if duration:
        duration_minutes = int(
            float(duration.group(1)) * (60 if duration.group(2).lower().startswith("hour") else 1)
        )
    if not sections:
        unresolved.append(
            "Section instructions did not match the explicit supported extraction grammar"
        )
    if total_marks is None:
        unresolved.append("Total marks not explicitly extracted")
    if duration_minutes is None:
        unresolved.append("Duration not explicitly extracted")
    if (
        sections
        and total_marks is not None
        and sum(item.maximum_marks or 0 for item in sections) != total_marks
    ):
        unresolved.append("Extracted section marks do not reconcile; sections retained for review")
        # Keep partial observations valid without falsely asserting a complete breakdown.
        sections = []
    if (
        sections
        and total_questions is not None
        and sum(item.question_count or 0 for item in sections) != total_questions
    ):
        unresolved.append("Extracted question counts do not reconcile; sections require review")
        sections = []
    return AssessmentPattern(
        status="review_required" if unresolved else "verified",
        total_marks=total_marks,
        duration_minutes=duration_minutes,
        total_questions=total_questions,
        sections=sections,
        unresolved_items=unresolved,
        source_locator=source_locator,
    )
