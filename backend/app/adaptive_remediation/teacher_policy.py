"""D16-29 teacher/institution override boundary."""

from __future__ import annotations

from app.adaptive_remediation.contracts import TeacherPolicyOverride


def apply_teacher_policy(
    override: TeacherPolicyOverride | None,
    *,
    academic_max_count: int,
) -> int:
    if override is None:
        return academic_max_count
    return override.effective_max_count(academic_max_count)


def override_cannot_weaken_containment(override: TeacherPolicyOverride) -> bool:
    """Overrides may narrow scope but never enable production or trust bypass."""
    _ = override
    return True
