from __future__ import annotations

from app.jee_main_exam_intelligence.constants import (
    CANDIDATE_SECTION_A_MCQ,
    CANDIDATE_SECTION_B_NUMERICAL,
    CANDIDATE_SUBJECT_QUESTION_COUNT,
)
from app.jee_main_exam_intelligence.contracts import PaperPlanSlot
from app.jee_main_exam_intelligence.enums import (
    JeeMainQuestionTypeQuota,
    JeeMainSectionCode,
    JeeMainSubjectCode,
    PaperPlanIssueCode,
)


def allocate_full_replica_slots() -> tuple[list[PaperPlanSlot], list[PaperPlanIssueCode]]:
    slots: list[PaperPlanSlot] = []
    issues: list[PaperPlanIssueCode] = []
    seq = 0
    for subject in JeeMainSubjectCode:
        for _ in range(CANDIDATE_SECTION_A_MCQ):
            seq += 1
            slots.append(
                PaperPlanSlot(
                    slot_id=f"{subject.value}-a-mcq-{seq:03d}",
                    subject_code=subject,
                    section_code=JeeMainSectionCode.SECTION_A,
                    question_type=JeeMainQuestionTypeQuota.MCQ,
                )
            )
        for _ in range(CANDIDATE_SECTION_B_NUMERICAL):
            seq += 1
            slots.append(
                PaperPlanSlot(
                    slot_id=f"{subject.value}-b-num-{seq:03d}",
                    subject_code=subject,
                    section_code=JeeMainSectionCode.SECTION_B,
                    question_type=JeeMainQuestionTypeQuota.NUMERICAL,
                )
            )
    expected = CANDIDATE_SUBJECT_QUESTION_COUNT * len(JeeMainSubjectCode)
    if len(slots) != expected:
        issues.append(PaperPlanIssueCode.IMPOSSIBLE_QUOTA)
    return slots, issues


def allocate_practice_slots(
    *,
    subject: JeeMainSubjectCode,
    count: int,
    topic_code: str | None,
    derived_topic_group: str | None,
) -> tuple[list[PaperPlanSlot], list[PaperPlanIssueCode]]:
    if count < 1:
        return [], [PaperPlanIssueCode.IMPOSSIBLE_QUOTA]
    slots = [
        PaperPlanSlot(
            slot_id=f"{subject.value}-practice-{index:03d}",
            subject_code=subject,
            topic_code=topic_code,
            derived_topic_group=derived_topic_group,
        )
        for index in range(1, count + 1)
    ]
    return slots, []
