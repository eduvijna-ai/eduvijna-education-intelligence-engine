from __future__ import annotations

from app.curriculum_intelligence.telangana_syllabus import (
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
