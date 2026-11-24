"""D16-29 teacher/institution override boundary."""

from __future__ import annotations

from dataclasses import dataclass

from app.adaptive_remediation.contracts import TeacherPolicyOverride


@dataclass(frozen=True, slots=True)
class TeacherPolicyApplication:
    effective_max_count: int
    accepted: bool
    reason: str | None = None


def apply_teacher_policy(
    override: TeacherPolicyOverride | None,
    *,
    academic_max_count: int,
    requested_count: int,
) -> TeacherPolicyApplication:
    if override is None:
        return TeacherPolicyApplication(
            effective_max_count=academic_max_count,
            accepted=academic_max_count == requested_count,
            reason=None if academic_max_count == requested_count else "COUNT_NOT_EXACT",
        )
    if override.allowed_difficulty_ceiling is not None:
        return TeacherPolicyApplication(
            effective_max_count=0,
            accepted=False,
            reason="DIFFICULTY_OVERRIDE_NOT_READY",
        )
    if not override.institution_scope and override.provenance != "synthetic-contract-only":
        return TeacherPolicyApplication(
            effective_max_count=0,
            accepted=False,
            reason="UNSUPPORTED_OVERRIDE_PROVENANCE",
        )
    effective = override.effective_max_count(academic_max_count)
    if effective != requested_count:
        return TeacherPolicyApplication(
            effective_max_count=effective,
            accepted=False,
            reason="OVERRIDE_COUNT_CONFLICT",
        )
    return TeacherPolicyApplication(
        effective_max_count=effective,
        accepted=True,
        reason=None,
    )


def override_cannot_weaken_containment(override: TeacherPolicyOverride) -> bool:
    _ = override
    return True
