from __future__ import annotations

import pytest

from app.curriculum_intelligence.telangana_syllabus import (
    TelanganaSyllabusParseError,
    parse_scert_syllabus_pdf,
    parse_scert_syllabus_text,
    parse_tgbie_annual_plan_text,
)

PS_FIXTURE = """
PHYSICAL SCIENCE - SYLLABUS
8th CLASS
1. Force
1.1 What is force ?
1.2 Types of forces
2. Friction
2.1 Force of friction - Types
"""

BS_FIXTURE = """
BIOLOGY -  SYLLABUS
8th CLASS
1. What is Science ?
1.1 Science - The individual perspective
2. Cell - The Basic Unit of Life
2.1 Discovery of the cell
"""

IA_PLAN_FIXTURE = """
TELANGANA BOARD OF INTERMEDIATE EDUCATION: HYDERABAD
ANNUAL ACADEMIC PLAN 2025-2026
MATHEMATICS-I (A) I YEAR
01. Functions: -
1.1 Types of functions
1.2 Inverse functions
"""


def test_parse_scert_physical_science_chapters() -> None:
    parsed = parse_scert_syllabus_text(PS_FIXTURE)
    assert parsed.subject_label == "Physical Science"
    assert parsed.chapters[0].title == "Force"
    assert "force" in parsed.chapters[0].topics[0].casefold()


def test_parse_scert_biological_science_chapters() -> None:
    parsed = parse_scert_syllabus_text(BS_FIXTURE)
    assert parsed.subject_label == "Biological Science"
    assert parsed.chapters[0].title == "What is Science ?"


def test_parse_tgbie_annual_plan_units() -> None:
    parsed = parse_tgbie_annual_plan_text(IA_PLAN_FIXTURE)
    assert parsed.subject_label == "Mathematics IA"
    assert parsed.chapters[0].title.startswith("Functions")


def test_multigrade_selection_never_mixes_chapters() -> None:
    text = PS_FIXTURE + "\nIX CLASS\n1. Motion\n1.1 Speed\nX CLASS\n1. Heat\n1.1 Temperature"
    with pytest.raises(TelanganaSyllabusParseError, match="Multiple classes"):
        parse_scert_syllabus_text(text)
    parsed = parse_scert_syllabus_text(text, grade="VIII")
    assert [c.title for c in parsed.chapters] == ["Force", "Friction"]
    assert parsed.chapters[0].topics == ("What is force ?", "Types of forces")
    assert parsed.grade_label == "VIII"
    assert parsed.academic_year is None
    assert parsed.academic_label == "unknown-year"


def test_no_invented_topic_or_academic_applicability() -> None:
    parsed = parse_scert_syllabus_text("PHYSICAL SCIENCE\nEdition 2025-26\nVIII CLASS\n1. Force")
    assert parsed.chapters[0].topics == ()
    assert parsed.academic_year is None


@pytest.mark.parametrize(
    "text",
    [
        PS_FIXTURE + "\n1. Force\n1.1 Duplicate",
        PS_FIXTURE.replace("1.2 Types of forces", "1.1 Duplicate"),
        PS_FIXTURE.replace("PHYSICAL SCIENCE", "SCIENCE"),
        PS_FIXTURE.replace("8th CLASS", ""),
    ],
)
def test_ambiguous_or_duplicate_source_rejected(text: str) -> None:
    with pytest.raises(TelanganaSyllabusParseError):
        parse_scert_syllabus_text(text)


@pytest.mark.parametrize(
    "paper,year,label",
    [
        ("MATHEMATICS-I (A)", "I YEAR", "Mathematics IA"),
        ("MATHEMATICS IB", "FIRST YEAR", "Mathematics IB"),
        ("MATHEMATICS-II (A)", "II YEAR", "Mathematics IIA"),
        ("MATHEMATICS IIB", "SECOND YEAR", "Mathematics IIB"),
    ],
)
def test_exact_intermediate_papers(paper: str, year: str, label: str) -> None:
    parsed = parse_tgbie_annual_plan_text(
        f"ACADEMIC PLAN 2025-2026\n{paper} {year}\n01. Functions\n1.1 Types"
    )
    assert parsed.subject_label == label
    assert parsed.academic_year == "2025-26"
    assert parsed.chapters[0].topics == ("Types",)


@pytest.mark.parametrize(
    "header", ["MATHEMATICS II YEAR", "PHYSICS I YEAR", "MATHEMATICS IA II YEAR", "MATHEMATICS IA"]
)
def test_unknown_or_conflicting_paper_not_guessed(header: str) -> None:
    with pytest.raises(TelanganaSyllabusParseError):
        parse_tgbie_annual_plan_text(header + "\n1. Functions\n1.1 Types")


def test_synthetic_pdf_retains_page_and_topic_locators() -> None:
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for lines in [
        ["PHYSICAL SCIENCE", "VIII CLASS", "1. Force", "1.1 Types"],
        ["VIII CLASS", "2. Friction", "2.1 Static friction"],
        ["IX CLASS", "1. Motion", "1.1 Speed"],
    ]:
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        commands = (
            "BT /F1 12 Tf 50 750 Td 20 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
        )
        stream.set_data(commands.encode())
        page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    parsed = parse_scert_syllabus_pdf(output.getvalue(), grade="VIII")
    assert len(parsed.chapters) == 2
    assert parsed.chapters[0].locator.startswith("page 1,")
    assert parsed.chapters[1].locator.startswith("page 2,")
    assert parsed.chapters[1].topic_locators[0].startswith("page 2,")
