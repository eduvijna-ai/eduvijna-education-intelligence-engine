"""Generic document semantics: authority is not interchangeable with purpose."""

from __future__ import annotations

from typing import Any

# SourceType represents trust/classification; these document domains represent
# what a source can prove. Explicitly conflicting labels never grant authority.
DOCUMENT_DOMAINS = {
    "education_framework": "framework",
    "curriculum_index": "syllabus",
    "curriculum_release_circular": "syllabus",
    "subject_syllabus": "syllabus",
    "annual_plan": "calendar",
    "syllabus": "syllabus",
    "syllabus_index": "syllabus",
    "textbook": "textbook",
    "textbook_index": "textbook",
    "learning_outcomes": "learning_outcome",
    "learning_outcome": "learning_outcome",
    "learning_outcome_index": "learning_outcome",
    "learning_standards": "academic_standard",
    "academic_standards": "academic_standard",
    "academic_standard": "academic_standard",
    "teacher_handbook": "pedagogy",
    "teacher_module": "pedagogy",
    "academic_calendar": "calendar",
    "assessment_evidence": "assessment",
    "sample_paper_index": "assessment",
    "sample_question_paper": "assessment",
    "marking_scheme": "assessment",
    "model_paper": "assessment",
    "publication_index": "catalogue",
    "authority_directory": "authority_reference",
}
_ALLOWED = {
    "membership": {"syllabus"},
    "framework": {"framework", "syllabus"},
    "framework_structure": {"framework", "syllabus", "academic_standard"},
    "outcome": {"learning_outcome", "academic_standard", "syllabus", "framework"},
    "competency": {"academic_standard", "learning_outcome", "framework", "syllabus"},
    "alignment": {"syllabus", "framework", "learning_outcome", "academic_standard"},
}


def source_domain(snapshot: dict[str, Any]) -> str | None:
    metadata = snapshot.get("metadata_json", {})
    if not isinstance(metadata, dict):
        return None
    inferred = DOCUMENT_DOMAINS.get(str(metadata.get("document_type", "")))
    explicit = metadata.get("source_domain")
    if explicit is not None and (
        explicit not in set(DOCUMENT_DOMAINS.values())
        or (inferred is not None and explicit != inferred)
    ):
        raise ValueError("conflicting or unknown source-domain classification")
    if snapshot.get("source_type") in {
        "sample_paper",
        "official_paper",
        "answer_key",
        "marking_scheme",
    }:
        return "assessment"
    return str(explicit) if explicit is not None else inferred


def require_domain(snapshot: dict[str, Any], purpose: str) -> None:
    domain = source_domain(snapshot)
    # Historical Day 2/3 callers without document types remain supported. All
    # manifest-driven curricula carry an explicit known document type; an unknown
    # declared type fails closed rather than masquerading as a legacy snapshot.
    metadata = snapshot.get("metadata_json", {})
    if domain is None:
        if isinstance(metadata, dict) and metadata.get("document_type"):
            raise ValueError("unknown document domain requires review")
        return
    if domain not in _ALLOWED[purpose]:
        raise ValueError(f"{domain} sources cannot establish {purpose} semantics")
