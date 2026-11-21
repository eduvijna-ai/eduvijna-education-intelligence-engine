"""Strict reference ExamBlueprintRule readiness (both papers, PCM, pinned sources)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jee_advanced.constants import (
    OFFICIAL_SUBJECTS,
    PAPER_1_CODE,
    PAPER_2_CODE,
    SOURCE_SLOT_PAPER1,
    SOURCE_SLOT_PAPER2,
    VERSION_REFERENCE_2026,
)
from app.jee_advanced.source_registry import _find_slot_source
from app.models import ExamBlueprintRule, ExamVersion, SourceRevision
from app.models.enums import BlueprintRuleType, SourceRevisionStatus

_COUNT_RULE_TYPES = frozenset(
    {
        BlueprintRuleType.QUESTION_COUNT.value,
        BlueprintRuleType.TOPIC_DISTRIBUTION.value,
    }
)


def _active_revision(session: Session, source_id: str) -> SourceRevision | None:
    return session.scalar(
        select(SourceRevision)
        .where(
            SourceRevision.source_id == source_id,
            SourceRevision.status == SourceRevisionStatus.ACTIVE.value,
        )
        .order_by(SourceRevision.revision_number.desc())
    )


def _slot_revision_pin(session: Session, slot_id: str) -> str | None:
    source = _find_slot_source(session, slot_id)
    if source is None:
        return None
    rev = _active_revision(session, str(source.id))
    return str(rev.id) if rev is not None else None


def reference_blueprint_issue_codes(session: Session, exam_version_id: str) -> tuple[str, ...]:
    version = session.get(ExamVersion, exam_version_id)
    if version is None:
        return ("exam_version_missing",)
    if version.version_code != VERSION_REFERENCE_2026:
        return ("not_reference_exam_version",)

    rules = session.scalars(
        select(ExamBlueprintRule).where(
            ExamBlueprintRule.exam_version_id == exam_version_id,
        )
    ).all()

    issues: list[str] = []
    paper_pins = {
        PAPER_1_CODE: SOURCE_SLOT_PAPER1,
        PAPER_2_CODE: SOURCE_SLOT_PAPER2,
    }
    for paper_code, slot_id in paper_pins.items():
        scoring = [
            r
            for r in rules
            if r.rule_type == BlueprintRuleType.SCORING.value
            and str((r.metadata_json or {}).get("paper_code") or "") == paper_code
        ]
        if not scoring:
            issues.append(f"{paper_code}:missing_scoring_rule")
            continue
        for row in scoring:
            if row.marks_per_question is None or row.negative_marks is None:
                issues.append(f"{paper_code}:incomplete_scoring_marks")
            selector = dict(row.selector_json or {})
            if selector.get("partial_marks") is None:
                issues.append(f"{paper_code}:missing_partial_policy")
            pin = str(selector.get("source_pinned_revision_id") or "")
            if not pin:
                issues.append(f"{paper_code}:scoring_source_unpinned")
            expected_pin = _slot_revision_pin(session, slot_id)
            if expected_pin and pin != expected_pin:
                issues.append(f"{paper_code}:scoring_revision_mismatch")

        subject_rules: dict[str, list[ExamBlueprintRule]] = {s: [] for s in OFFICIAL_SUBJECTS}
        for row in rules:
            meta = dict(row.metadata_json or {})
            if str(meta.get("paper_code") or "") != paper_code:
                continue
            if row.rule_type not in _COUNT_RULE_TYPES:
                continue
            count_ok = row.exact_count is not None or row.min_count is not None
            if not count_ok:
                continue
            pin = str((row.selector_json or {}).get("source_pinned_revision_id") or "")
            if not pin:
                issues.append(f"{paper_code}:count_rule_unpinned")
                continue
            for subj in meta.get("subjects") or []:
                key = str(subj).lower()
                if key in subject_rules:
                    subject_rules[key].append(row)

        for subj in OFFICIAL_SUBJECTS:
            if not subject_rules[subj]:
                issues.append(f"{paper_code}:missing_{subj}_quota_rule")

    return tuple(dict.fromkeys(issues))


def reference_blueprint_ready(session: Session, exam_version_id: str) -> bool:
    return len(reference_blueprint_issue_codes(session, exam_version_id)) == 0