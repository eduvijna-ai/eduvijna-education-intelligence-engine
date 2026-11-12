from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.jee_main_exam_intelligence.constants import DERIVED_TOPIC_ALGEBRA, DERIVED_TOPIC_LABEL
from app.jee_main_exam_intelligence.enums import (
    JeeMainSubjectCode,
    PaperPlanIssueCode,
    SyllabusTopicKind,
)

OFFICIAL_JEE_MAIN_2027_TOPICS: dict[str, list[dict[str, Any]]] = {
    JeeMainSubjectCode.MATHEMATICS.value: [
        {
            "topic_code": "sets-relations-functions",
            "title": "Sets, Relations and Functions",
            "kind": SyllabusTopicKind.OFFICIAL_NTA_UNIT.value,
            "source_locator": "syllabus-2027:mathematics:unit-1",
        },
        {
            "topic_code": "complex-numbers-quadratic",
            "title": "Complex Numbers and Quadratic Equations",
            "kind": SyllabusTopicKind.OFFICIAL_NTA_UNIT.value,
            "source_locator": "syllabus-2027:mathematics:unit-2",
        },
        {
            "topic_code": "matrices-determinants",
            "title": "Matrices and Determinants",
            "kind": SyllabusTopicKind.OFFICIAL_NTA_UNIT.value,
            "source_locator": "syllabus-2027:mathematics:unit-3",
        },
    ],
    JeeMainSubjectCode.PHYSICS.value: [
        {
            "topic_code": "units-measurements",
            "title": "Units and Measurements",
            "kind": SyllabusTopicKind.OFFICIAL_NTA_UNIT.value,
            "source_locator": "syllabus-2027:physics:unit-1",
        },
    ],
    JeeMainSubjectCode.CHEMISTRY.value: [
        {
            "topic_code": "some-basic-concepts",
            "title": "Some Basic Concepts in Chemistry",
            "kind": SyllabusTopicKind.OFFICIAL_NTA_UNIT.value,
            "source_locator": "syllabus-2027:chemistry:unit-1",
        },
    ],
}

DERIVED_TOPIC_GROUPS: dict[str, dict[str, Any]] = {
    DERIVED_TOPIC_ALGEBRA: {
        "label": DERIVED_TOPIC_LABEL,
        "kind": SyllabusTopicKind.DERIVED_EDUVIJNA_GROUP.value,
        "constituent_official_topic_codes": [
            "complex-numbers-quadratic",
            "matrices-determinants",
        ],
        "subject_code": JeeMainSubjectCode.MATHEMATICS.value,
    },
}


def validate_subject_code(subject_code: str) -> JeeMainSubjectCode | None:
    try:
        return JeeMainSubjectCode(subject_code)
    except ValueError:
        return None


def resolve_topic_codes(
    *,
    subject_code: JeeMainSubjectCode,
    topic_code: str | None,
    derived_topic_group: str | None,
) -> tuple[list[str], list[PaperPlanIssueCode]]:
    issues: list[PaperPlanIssueCode] = []
    if derived_topic_group:
        group = DERIVED_TOPIC_GROUPS.get(derived_topic_group)
        if group is None:
            issues.append(PaperPlanIssueCode.UNKNOWN_TOPIC)
            return [], issues
        if group["subject_code"] != subject_code.value:
            issues.append(PaperPlanIssueCode.OUT_OF_SYLLABUS)
            return [], issues
        return list(group["constituent_official_topic_codes"]), issues
    if topic_code:
        official = OFFICIAL_JEE_MAIN_2027_TOPICS.get(subject_code.value, [])
        codes = {row["topic_code"] for row in official}
        if topic_code not in codes:
            issues.append(PaperPlanIssueCode.UNKNOWN_TOPIC)
            return [], issues
        return [topic_code], issues
    return [], issues


def syllabus_guard_passes(
    session: Session,
    *,
    subject_code: str,
    topic_code: str | None,
    derived_topic_group: str | None,
    approved_syllabus_revision_ids: list[str] | None,
) -> tuple[bool, list[PaperPlanIssueCode]]:
    # Catalogue is versioned via constants until full syllabus ingest.
    del session, approved_syllabus_revision_ids
    subject = validate_subject_code(subject_code)
    if subject is None:
        return False, [PaperPlanIssueCode.UNKNOWN_SUBJECT]
    _, issues = resolve_topic_codes(
        subject_code=subject,
        topic_code=topic_code,
        derived_topic_group=derived_topic_group,
    )
    return len(issues) == 0, issues
