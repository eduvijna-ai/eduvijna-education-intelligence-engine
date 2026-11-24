"""D16-03 runtime containment — production learner remediation unconditionally disabled."""

from __future__ import annotations

CONTAINMENT_MILESTONE = "D16-SAFETY-CONTAINMENT-01"
PRODUCTION_REMEDIATION_DISABLED = True
SYNTHETIC_DIAGNOSTIC_ONLY = True
DAY14_ACADEMIC_VALIDATION_PRESERVED = True
DAY14_ISSUANCE_DISABLED_PRESERVED = True

CONTAINMENT_NOTE = (
    "Real learner remediation, issuance, scheduling, persistence and mastery updates are "
    "unconditionally NOT_READY pending Day15 authorization and academic gates. "
    "Outputs are non-actionable synthetic diagnostics only."
)

FORBIDDEN_RUNTIME_TYPES = frozenset(
    {
        "sqlalchemy.orm.session.Session",
        "sqlalchemy.orm.scoping.scoped_session",
    }
)
