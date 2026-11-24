"""Day15 safety containment (D15-SAFETY-CONTAINMENT-01).

All learner-intelligence runtime database I/O is disabled until trusted
production authorization exists (deferred; Day17+).
"""

from __future__ import annotations

from app.learner_intelligence.enums import IssueCode

# Explicit capability flags for verifiers and governance (not caller-controlled).
CONTAINMENT_ACTIVE: bool = True
PRODUCTION_ASSESSMENT_ELIGIBILITY: bool = False
TRUSTED_LEARNER_PERSISTENCE: bool = False
TRUSTED_ACADEMIC_SCORING: bool = False
TRUSTED_MASTERY_EVIDENCE: bool = False
TRUSTED_DIAGNOSTIC_READINESS: bool = False
DAY16_HANDOFF_READINESS: bool = False
DURABLE_LEARNER_EVIDENCE: bool = False


def runtime_learner_db_io_allowed() -> bool:
    """Unconditional fail-closed for all public/runtime Day15 DB boundaries."""

    return False


def containment_issue() -> IssueCode:
    return IssueCode.NOT_READY