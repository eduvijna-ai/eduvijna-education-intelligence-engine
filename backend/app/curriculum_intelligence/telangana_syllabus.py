"""Conservative source-bound Telangana heading extraction; no applicability inference."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.curriculum_intelligence.scoped_catalogue import checked_text


class TelanganaSyllabusParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedChapter:
    number: str
    title: str
    locator: str
    topics: tuple[str, ...]
    topic_locators: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedSyllabus:
    academic_label: str
    subject_label: str
    chapters: tuple[ParsedChapter, ...]
    grade_label: str | None = None
    academic_year: str | None = None


_CLASS_LABEL = re.compile(
    r"(?:(?P<before>VIII|VII|VI|IV|IX|III|II|X|V|I|10|[1-9])(?:th|st|nd|rd)?\s*CLASS\b"
    r"|\bCLASS\s*(?P<after>VIII|VII|VI|IV|IX|III|II|X|V|I|10|[1-9])\b)",
    re.I,
)
_CHAPTER = re.compile(r"^\s*(\d{1,2})\.\s+([^\n]+?)\s*$")
_TOPIC = re.compile(r"^\s*(\d+(?:\.\d+)+)\s+(.+?)\s*$")
_GRADES = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def _grade(value: str) -> str:
    value = value.upper()
    return _GRADES[int(value) - 1] if value.isdigit() else value


def _pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        # Form feeds preserve exact PDF page boundaries throughout extraction.
        text = "\f".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise TelanganaSyllabusParseError("PDF could not be extracted") from exc
    if not text.strip():
        raise TelanganaSyllabusParseError("PDF has no extractable text")
    return text


def _academic_year(text: str) -> str | None:
    # Edition dates and arbitrary year numbers are deliberately not applicability.
    matches = re.findall(
        r"(?:ACADEMIC\s+(?:YEAR|PLAN))\s*[:\-]?\s*(20\d{2})\s*[-–]\s*(20\d{2}|\d{2})",
        text,
        re.I,
    )
    years = {f"{start}-{end[-2:]}" for start, end in matches}
    if len(years) > 1:
        raise TelanganaSyllabusParseError("Conflicting academic years require review")
    return next(iter(years), None)


def _chapters(text: str, *, selected_grade: str | None = None) -> tuple[ParsedChapter, ...]:
    current_grade = None
    chapters: list[ParsedChapter] = []
    pending: tuple[str, str, str] | None = None
    topics: list[str] = []
    locators: list[str] = []
    seen: set[str] = set()
    topic_numbers: set[str] = set()

    def flush() -> None:
        nonlocal pending, topics, locators, topic_numbers
        if pending:
            chapters.append(ParsedChapter(*pending, tuple(topics), tuple(locators)))
        pending, topics, locators, topic_numbers = None, [], [], set()

    for page, body in enumerate(text.split("\f"), 1):
        for line_num, line in enumerate(body.splitlines(), 1):
            class_match = _CLASS_LABEL.search(line)
            if class_match:
                new_grade = _grade(class_match.group("before") or class_match.group("after"))
                if new_grade != current_grade:
                    flush()
                current_grade = new_grade
                continue
            if selected_grade is not None and current_grade != selected_grade:
                continue
            heading = _CHAPTER.match(line)
            if heading:
                flush()
                number, title = heading.groups()
                number = str(int(number))
                if number in seen:
                    raise TelanganaSyllabusParseError(f"Duplicate chapter number {number}")
                seen.add(number)
                title = checked_text(title.strip(" :-"))
                pending = (
                    number,
                    title,
                    f"page {page}, line {line_num}, section {number}. {title}",
                )
                continue
            topic = _TOPIC.match(line)
            if topic:
                number, title = topic.groups()
                if pending is None or int(number.split(".")[0]) != int(pending[0]):
                    raise TelanganaSyllabusParseError("Topic outside its chapter requires review")
                if number in topic_numbers:
                    raise TelanganaSyllabusParseError(f"Duplicate topic number {number}")
                topic_numbers.add(number)
                topics.append(checked_text(title))
                locators.append(f"page {page}, line {line_num}, section {number}")
    flush()
    if not chapters:
        raise TelanganaSyllabusParseError("No numbered syllabus chapters found")
    return tuple(chapters)


def parse_scert_syllabus_text(text: str, *, grade: str | None = None) -> ParsedSyllabus:
    grades = {_grade(m.group("before") or m.group("after")) for m in _CLASS_LABEL.finditer(text)}
    if not grades:
        raise TelanganaSyllabusParseError("Missing explicit class identity")
    if grade is None and len(grades) != 1:
        raise TelanganaSyllabusParseError("Multiple classes require an explicit grade selection")
    selected = _grade(grade) if grade else next(iter(grades))
    if selected not in grades:
        raise TelanganaSyllabusParseError("Requested class not present")
    subjects = []
    if re.search(r"\bPHYSICAL\s+SCIENCE\b", text, re.I):
        subjects.append("Physical Science")
    if re.search(r"\b(?:BIOLOGY|BIOLOGICAL\s+SCIENCE|BIO\.?\s+SCIENCE)\b", text, re.I):
        subjects.append("Biological Science")
    if len(subjects) != 1:
        raise TelanganaSyllabusParseError("Missing or ambiguous explicit subject identity")
    year = _academic_year(text)
    return ParsedSyllabus(
        year or "unknown-year",
        subjects[0],
        _chapters(text, selected_grade=selected),
        selected,
        year,
    )


def parse_scert_syllabus_pdf(content: bytes, *, grade: str | None = None) -> ParsedSyllabus:
    return parse_scert_syllabus_text(_pdf_text(content), grade=grade)


def parse_tgbie_annual_plan_text(text: str) -> ParsedSyllabus:
    matches = re.findall(
        r"\b(?:MATHEMATICS|MATHS)\s*[-–]?\s*(II|I)\s*\(?\s*([AB])\s*\)?\b", text, re.I
    )
    subjects = {f"Mathematics {year.upper()}{paper.upper()}" for year, paper in matches}
    if len(subjects) != 1:
        raise TelanganaSyllabusParseError("Missing or ambiguous explicit mathematics paper")
    subject = next(iter(subjects))
    years = set(re.findall(r"\b(II|I|FIRST|SECOND|1ST|2ND)\s+YEAR\b", text, re.I))
    grades = {"First Year" if y.upper() in {"I", "FIRST", "1ST"} else "Second Year" for y in years}
    if len(grades) != 1:
        raise TelanganaSyllabusParseError("Missing or ambiguous Intermediate year")
    grade = next(iter(grades))
    if ("II" in subject) != (grade == "Second Year"):
        raise TelanganaSyllabusParseError("Paper and Intermediate year conflict")
    year = _academic_year(text)
    return ParsedSyllabus(year or "unknown-year", subject, _chapters(text), grade, year)


def parse_tgbie_annual_plan_pdf(content: bytes) -> ParsedSyllabus:
    return parse_tgbie_annual_plan_text(_pdf_text(content))
