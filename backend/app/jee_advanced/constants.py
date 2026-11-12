from __future__ import annotations

JEE_ADVANCED_PACK_CODE = "jee_advanced"
JEE_ADVANCED_AUTHORITY = "IIT Joint Admission Board (JAB)"

VERSION_SYNTHETIC_DEMO = "synthetic-demo-v1"
VERSION_REFERENCE_2026 = "reference-2026"
VERSION_CANDIDATE_2027 = "candidate-2027"

PAPER_1_CODE = "paper_1"
PAPER_2_CODE = "paper_2"

SUBJECT_PHYSICS = "physics"
SUBJECT_CHEMISTRY = "chemistry"
SUBJECT_MATHEMATICS = "mathematics"

OFFICIAL_SUBJECTS = (
    SUBJECT_PHYSICS,
    SUBJECT_CHEMISTRY,
    SUBJECT_MATHEMATICS,
)

# Brochure Clause 17: two compulsory papers, three hours each (documented official fact).
REFERENCE_PAPER_DURATION_MINUTES = 180

# Discovery URLs for curator ingest — bytes and SHA are recorded only after real ingest.
OFFICIAL_DISCOVERY_URLS: dict[str, str] = {
    "brochure_en_2026": "https://jeeadv.ac.in/documents/IBEnglish_2026.pdf",
    "syllabus_2026": "https://jeeadv.ac.in/documents/jee-advanced-2026-syllabus.pdf",
    "site_home": "https://jeeadv.ac.in/",
    "archive": "https://jeeadv.ac.in/archive.html",
}

SOURCE_SLOT_BROCHURE = "jee_advanced.2026.brochure"
SOURCE_SLOT_SYLLABUS = "jee_advanced.2026.syllabus"
SOURCE_SLOT_PAPER1 = "jee_advanced.2026.paper_1"
SOURCE_SLOT_PAPER2 = "jee_advanced.2026.paper_2"
SOURCE_SLOT_KEY_PAPER1 = "jee_advanced.2026.key_paper_1"
SOURCE_SLOT_KEY_PAPER2 = "jee_advanced.2026.key_paper_2"

EDUVIJNA_DERIVED_TOPIC_GROUP = "algebra"
MATHEMATICS_SUBJECT = SUBJECT_MATHEMATICS

# Demonstration-only per-paper PCM quotas (not official JEE Advanced counts).
SYNTHETIC_SUBJECT_QUOTA_PER_PAPER: dict[str, int] = {
    SUBJECT_PHYSICS: 2,
    SUBJECT_CHEMISTRY: 2,
    SUBJECT_MATHEMATICS: 2,
}
SYNTHETIC_DEFAULT_ITEMS_PER_PAPER = sum(SYNTHETIC_SUBJECT_QUOTA_PER_PAPER.values())
SYNTHETIC_MAX_ITEMS_PER_PAPER = 30
