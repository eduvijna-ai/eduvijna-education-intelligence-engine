"""Parse reviewed Telangana syllabus and annual-plan text; no network access."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.curriculum_intelligence.scoped_catalogue import checked_text
from app.source_intelligence.extractors import normalize_text


class TelanganaSyllabusParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedChapter:
    number: str
    title: str
    locator: str
    topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedSyllabus:
    academic_label: str
    subject_label: str
    chapters: tuple[ParsedChapter, ...]


_CHAPTER_HEAD = re.compile(
    r"(?P<num>\d{1,2})\.\s+(?P<title>[A-Za-z][^\n\d]{2,80}?)(?=\s*(?:\d+\.\d|\n|$))",
)
_CLASS_LABEL = re.compile(
    r"(?P<label>(?:[IVXLC]+|\d+)(?:th|st|nd|rd)?\s*CLASS)",
    re.IGNORECASE,
)
_TOPIC = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)+)\s+(?P<body>.+?)\s*$", re.MULTILINE)


def _pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise TelanganaSyllabusParseError("PDF could not be opened") from exc
    text = normalize_text("\n".join(page.extract_text() or "" for page in reader.pages))
    if len(text.strip()) < 40:
        raise TelanganaSyllabusParseError("PDF has no extractable text")
    return text


def _split_chapters(body: str) -> list[tuple[str, str]]:
    normalized = re.sub(r"(CLASS)\s*(\d{1,2}\.)", r"\1\n\2", body, flags=re.IGNORECASE)
    matches = list(_CHAPTER_HEAD.finditer(normalized))
    if not matches:
        raise TelanganaSyllabusParseError("No numbered syllabus chapters found")
    chapters: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in matches:
        num = match.group("num")
        title = checked_text(match.group("title").strip(" :-"))
        key = f"{num}|{title.casefold()}"
        if key in seen:
            continue
        seen.add(key)
        chapters.append((num, title))
    return chapters


def _topics_for_chapter(body: str, chapter_num: str) -> tuple[str, ...]:
    topics = tuple(
        checked_text(match.group("body").strip())
        for match in _TOPIC.finditer(body)
        if match.group("num").startswith(chapter_num + ".")
    )
    return topics or (f"{chapter_num}.1 syllabus topic",)


def parse_scert_syllabus_text(text: str) -> ParsedSyllabus:
    normalized = normalize_text(text)
    class_match = _CLASS_LABEL.search(normalized)
    academic_label = class_match.group("label") if class_match else "unknown-class"
    if "PHYSICAL SCIENCE" in normalized.upper():
        subject = "Physical Science"
    elif "BIOLOGY" in normalized.upper():
        subject = "Biological Science"
    else:
        subject = "Science"
    body = normalized[class_match.end() :] if class_match else normalized
    chapters = tuple(
        ParsedChapter(
            number=num,
            title=title,
            locator=f"syllabus section {num}. {title}",
            topics=_topics_for_chapter(body, num),
        )
        for num, title in _split_chapters(body)
    )
    return ParsedSyllabus(
        academic_label=checked_text(academic_label),
        subject_label=checked_text(subject),
        chapters=chapters,
    )


def parse_scert_syllabus_pdf(content: bytes) -> ParsedSyllabus:
    return parse_scert_syllabus_text(_pdf_text(content))


def parse_tgbie_annual_plan_text(text: str) -> ParsedSyllabus:
    normalized = normalize_text(text)
    year_match = re.search(r"(20\d{2}-20\d{2})", normalized)
    academic_label = year_match.group(1) if year_match else "unknown-year"
    upper = normalized.upper()
    if "MATHEMATICS-II" in upper or "MATHS-II" in upper:
        subject = "Mathematics IIA"
    elif "MATHEMATICS IB" in upper:
        subject = "Mathematics IB"
    else:
        subject = "Mathematics IA"
    if _CHAPTER_HEAD.search(normalized):
        chapters = tuple(
            ParsedChapter(
                number=num,
                title=title,
                locator=f"annual plan unit {num}. {title}",
                topics=_topics_for_chapter(normalized, num),
            )
            for num, title in _split_chapters(normalized)
        )
    else:
        unit_match = re.search(
            r"(?P<num>0?\d+)\.?\s+(?P<title>[A-Za-z][^\n:]{2,80})",
            normalized,
        )
        if unit_match is None:
            raise TelanganaSyllabusParseError("No annual-plan unit headings found")
        num = unit_match.group("num")
        title = checked_text(unit_match.group("title").strip())
        chapters = (
            ParsedChapter(
                number=num,
                title=title,
                locator=f"annual plan unit {num}. {title}",
                topics=_topics_for_chapter(normalized, num),
            ),
        )
    return ParsedSyllabus(
        academic_label=checked_text(academic_label),
        subject_label=checked_text(subject),
        chapters=chapters,
    )


def parse_tgbie_annual_plan_pdf(content: bytes) -> ParsedSyllabus:
    return parse_tgbie_annual_plan_text(_pdf_text(content))
