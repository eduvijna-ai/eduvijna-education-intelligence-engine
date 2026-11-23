"""CUET / CLAT pack codes, official pattern metadata, and discovery URLs."""

from __future__ import annotations

CUET_PACK_CODE = "cuet_ug"
CLAT_PACK_CODE = "clat_ug"

CUET_AUTHORITY = "NTA"
CLAT_AUTHORITY = "Consortium_of_NLUs"

VERSION_CUET_REFERENCE_2026 = "cuet_ug_2026_reference"
VERSION_CUET_2027_UNVERIFIED = "cuet_ug_2027_not_verified"
VERSION_CLAT_2027 = "clat_ug_2027"
VERSION_SYNTHETIC_DEMO = "cuet_clat_synthetic_demo"

MATHEMATICS_DOMAIN = "domain_mathematics"
GENERAL_APTITUDE = "general_aptitude"
MAX_CUET_TESTS_SELECTED = 5

CUET_QUESTIONS_PER_TEST = 50
CUET_MINUTES_PER_TEST = 60
CUET_MARK_CORRECT = 5.0
CUET_MARK_INCORRECT = -1.0

CLAT_TOTAL_QUESTIONS = 120
CLAT_TOTAL_MINUTES = 120
CLAT_MARK_CORRECT = 1.0
CLAT_MARK_INCORRECT = -0.25
CLAT_MARK_BLANK = 0.0

CLAT_SECTION_RANGES: dict[str, tuple[int, int]] = {
    "english": (22, 26),
    "current_affairs_gk": (28, 32),
    "legal_reasoning": (28, 32),
    "logical_reasoning": (22, 26),
    "quantitative_techniques": (10, 14),
}

CUET_TEST_CATALOGUE_SIZE = 37  # 13 languages + 23 domains + General Aptitude

PRIMARY_SOURCE_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "exam": "cuet_ug",
        "year": "2026",
        "kind": "information_bulletin",
        "url": "https://cdnbbsr.s3waas.gov.in/s3d1a21da7bca4abff8b0b61b87597de73/uploads/2026/01/202601031633478370.pdf",
        "locator": "page_15",
        "rights_status": "SOURCE_PENDING",
    },
    {
        "exam": "cuet_ug",
        "year": "2026",
        "kind": "syllabus_index",
        "url": "https://cuet.nta.nic.in/cuetug-2026-syllabus/",
        "locator": "subject_catalogue",
        "rights_status": "SOURCE_PENDING",
    },
    {
        "exam": "clat_ug",
        "year": "2027",
        "kind": "question_format",
        "url": "https://clat2027.consortiumofnlus.ac.in/clat-2027/ug-question-format.html",
        "locator": "format_rules",
        "rights_status": "SOURCE_PENDING",
    },
    {
        "exam": "clat_ug",
        "year": "2027",
        "kind": "syllabus",
        "url": "https://clat2027.consortiumofnlus.ac.in/clat-2027/ug-syllabus.html",
        "locator": "section_syllabus",
        "rights_status": "SOURCE_PENDING",
    },
)