from __future__ import annotations

from app.knowledge_intelligence.contracts import AppliedKnowledgeScope, KnowledgeContextPack
from app.orchestration.contracts import ResolvedScope


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def validate_context_scope(
    resolved: ResolvedScope, pack: KnowledgeContextPack
) -> list[str]:
    """Return blocking issue codes when Day 7 pack scope does not match resolved scope."""
    issues: list[str] = []
    applied: AppliedKnowledgeScope = pack.scope

    pairs: list[tuple[str, str | None, str | None]] = [
        ("organization_id", resolved.organization_id, applied.organization_id),
        ("institution_id", resolved.institution_id, applied.institution_id),
        ("teacher_id", resolved.teacher_id, applied.teacher_id),
        ("curriculum_version_id", resolved.curriculum_version_id, applied.curriculum_version_id),
        ("exam_version_id", resolved.exam_version_id, applied.exam_version_id),
        ("grade_year_code", resolved.grade_year_code, applied.grade_year_code),
        ("medium_code", resolved.medium_code, applied.medium_code),
        ("subject_code", resolved.subject_code, applied.subject_code),
    ]
    for field, expected, observed in pairs:
        exp = _norm(expected)
        if exp is None:
            continue
        obs = _norm(observed)
        if obs is not None and obs != exp:
            issues.append(f"scope_mismatch:{field}")

    if resolved.topic_codes:
        missing = set(resolved.topic_codes) - set(applied.topic_codes or [])
        if missing:
            issues.append("scope_mismatch:topic_codes")
    if resolved.concept_codes:
        missing = set(resolved.concept_codes) - set(applied.concept_codes or [])
        if missing:
            issues.append("scope_mismatch:concept_codes")

    if not pack.evidence and any(
        _norm(value) is not None
        for value in (
            resolved.curriculum_version_id,
            resolved.exam_version_id,
            resolved.organization_id,
        )
    ):
        issues.append("scope_empty_evidence")

    return issues
