from __future__ import annotations

from app.jee_advanced.constants import (
    JEE_ADVANCED_PACK_CODE,
    MATHEMATICS_SUBJECT,
    OFFICIAL_SUBJECTS,
)
from app.jee_advanced.enums import AdvancedIssueCode


def validate_exam_pack_scope(exam_pack_code: str) -> list[AdvancedIssueCode]:
    if exam_pack_code != JEE_ADVANCED_PACK_CODE:
        return [AdvancedIssueCode.WRONG_EXAM_PACK, AdvancedIssueCode.JEE_MAIN_FALLBACK]
    return []


def validate_subject_scope(subject_code: str) -> list[AdvancedIssueCode]:
    normalized = subject_code.strip().lower()
    if normalized not in OFFICIAL_SUBJECTS:
        return [AdvancedIssueCode.WRONG_SUBJECT]
    return []


def validate_mathematics_topic(topic_group: str, *, subject_code: str) -> list[AdvancedIssueCode]:
    issues = validate_subject_scope(subject_code)
    if issues:
        return issues
    if subject_code.strip().lower() != MATHEMATICS_SUBJECT:
        return [AdvancedIssueCode.WRONG_SUBJECT]
    if not topic_group.strip():
        return [AdvancedIssueCode.WRONG_TOPIC]
    return []
