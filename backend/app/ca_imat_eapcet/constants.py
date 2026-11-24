"""CA Foundation, IMAT, and TG EAPCET pack metadata and primary-source manifest."""

from __future__ import annotations

CA_FOUNDATION_PACK_CODE = "ca_foundation"
IMAT_PACK_CODE = "imat"
EAPCET_PACK_CODE = "tg_eapcet"

CA_AUTHORITY = "ICAI"
IMAT_AUTHORITY = "MUR_Italy"
EAPCET_AUTHORITY = "TGCHE"

VERSION_CA_SYNTHETIC_DEMO = "ca_foundation_synthetic_demo"
VERSION_CA_SESSION_JAN2027 = "ca_foundation_jan2027"
VERSION_CA_FUTURE_UNVERIFIED = "ca_foundation_future_unverified"

VERSION_IMAT_2026_REF = "imat_2026_dm1005_reference"
VERSION_IMAT_FUTURE_UNVERIFIED = "imat_future_unverified"

VERSION_EAPCET_SYNTHETIC = "eapcet_synthetic_demo"
VERSION_EAPCET_ENGINEERING_2026 = "eapcet_engineering_2026"
VERSION_EAPCET_AGRICULTURE_PHARMACY_2026 = "eapcet_agriculture_pharmacy_2026"

CA_PAPER_CODES: tuple[str, ...] = (
    "paper1_accounting",
    "paper2_business_laws",
    "paper3_quantitative_aptitude",
    "paper4_business_economics",
)

CA_PAPER_KIND: dict[str, str] = {
    "paper1_accounting": "descriptive",
    "paper2_business_laws": "descriptive",
    "paper3_quantitative_aptitude": "objective",
    "paper4_business_economics": "objective",
}

CA_MARKS_PER_PAPER = 100
CA_OBJECTIVE_NEGATIVE_MARK = 0.0  # no penalty unless source attests; synthetic uses 0

IMAT_TOTAL_QUESTIONS = 60
IMAT_TOTAL_MINUTES = 100
IMAT_MARK_CORRECT = 1.5
IMAT_MARK_BLANK = 0.0
IMAT_MARK_INCORRECT = 0.0
IMAT_OPTIONS_PER_QUESTION = 5

EAPCET_ENGINEERING_SECTIONS: dict[str, int] = {
    "mathematics": 80,
    "physics": 40,
    "chemistry": 40,
}
EAPCET_TOTAL_QUESTIONS = 160
EAPCET_TOTAL_MINUTES = 180
EAPCET_MARK_CORRECT = 1.0
EAPCET_MARK_BLANK = 0.0
EAPCET_MARK_INCORRECT = 0.0

EAPCET_AP_SECTIONS_REFERENCE: dict[str, int] = {
    "botany": 40,
    "zoology": 40,
    "physics": 40,
    "chemistry": 40,
}

PRIMARY_SOURCE_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "exam": "ca_foundation",
        "session": "jan2027",
        "kind": "scheme_nset",
        "url": "https://www.icai.org/post/foundation-nset",
        "locator": "scheme_overview",
        "rights_status": "SOURCE_PENDING",
        "discovery_only": "false",
    },
    {
        "exam": "ca_foundation",
        "session": "jan2027",
        "kind": "syllabus",
        "url": "https://www.icai.org/post/syllabus-nset-fnd",
        "locator": "four_papers",
        "rights_status": "SOURCE_PENDING",
        "discovery_only": "false",
    },
    {
        "exam": "ca_foundation",
        "session": "jan2027",
        "kind": "rtp",
        "url": "https://www.icai.org/post/rtp-foundation-course-jan2027",
        "locator": "revision_test_papers",
        "rights_status": "SOURCE_PENDING",
        "discovery_only": "false",
    },
    {
        "exam": "imat",
        "year": "2026",
        "kind": "ministerial_decree",
        "url": "https://www.mur.gov.it/it/atti-e-normativa/decreto-ministeriale-n-1005-del-06-08-2026",
        "locator": "dm_1005",
        "rights_status": "SOURCE_PENDING",
        "discovery_only": "false",
    },
    {
        "exam": "imat",
        "year": "2026",
        "kind": "accesso_annex",
        "url": "https://accessoprogrammato.mur.gov.it/2026/index.php?pag=IMT5",
        "locator": "annex_sections",
        "rights_status": "SOURCE_PENDING",
        "discovery_only": "false",
    },
    {
        "exam": "tg_eapcet",
        "year": "2026",
        "stream": "engineering",
        "kind": "official_portal",
        "url": "https://eapcet.tgche.ac.in",
        "locator": "notifications",
        "rights_status": "SOURCE_PENDING",
        "discovery_only": "false",
    },
    {
        "exam": "tg_eapcet",
        "year": "2026",
        "stream": "engineering",
        "kind": "discovery_mirror_booklet",
        "url": "https://docs.aglasem.com/view/8152b1f6-1a08-11f1-9297-0a5e36bc6706",
        "locator": "engineering_booklet_mirror",
        "rights_status": "SOURCE_PENDING",
        "discovery_only": "true",
    },
)

GENERIC_ENGINE_MODULES: tuple[str, ...] = (
    "app.models.examination",
    "app.cuet_clat.practice_service",
    "app.jee_advanced.planner",
)