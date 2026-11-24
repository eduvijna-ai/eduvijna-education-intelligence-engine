"""D16-29 teacher/institution override boundary."""

from __future__ import annotations

from dataclasses import dataclass

from app.adaptive_remediation.contracts import TeacherPolicyOverride
from app.adaptive_remediation.validation import require_exact_model

_ALLOWED_PROVENANCE = "synthetic-contract-only"


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
    typed = require_exact_model(override, TeacherPolicyOverride)
    if typed is None:
        return TeacherPolicyApplication(
            effective_max_count=0,
            accepted=False,
            reason="INVALID_OVERRIDE_TYPE",
        )
    override = typed  # type: ignore[assignment]
    if override.provenance != _ALLOWED_PROVENANCE:
        return TeacherPolicyApplication(
            effective_max_count=0,
            accepted=False,
            reason="UNSUPPORTED_OVERRIDE_PROVENANCE",
        )
    if override.allowed_difficulty_ceiling is not None:
        return TeacherPolicyApplication(
            effective_max_count=0,
            accepted=False,
            reason="DIFFICULTY_OVERRIDE_NOT_READY",
        )
    return TeacherPolicyApplication(
        effective_max_count=0,
        accepted=False,
        reason="TEACHER_OVERRIDE_NOT_READY",
    )


def override_cannot_weaken_containment(override: TeacherPolicyOverride) -> bool:
    typed = require_exact_model(override, TeacherPolicyOverride)
    return typed is not None