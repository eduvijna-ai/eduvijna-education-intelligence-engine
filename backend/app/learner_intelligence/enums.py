from __future__ import annotations

from enum import StrEnum

MASTERY_POLICY_VERSION = "mastery-policy@v1"


class AttemptState(StrEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    FINALIZED = "finalized"
    ABANDONED = "abandoned"


class EligibilityVerdict(StrEnum):
    ELIGIBLE = "eligible"
    BLOCKED_CONTAINMENT = "blocked_containment"
    BLOCKED_UNVERIFIED = "blocked_unverified"
    BLOCKED_FORGED_APPROVAL = "blocked_forged_approval"
    BLOCKED_TENANT = "blocked_tenant"
    BLOCKED_SCOPE = "blocked_scope"


class EligibilityTrustMode(StrEnum):
    """Trusted paths for Day 15; production official paths remain blocked under D14 containment."""

    SYNTHETIC_D15_HARNESS = "synthetic_d15_harness"


class ScoringVerdict(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    BLANK = "blank"
    PARTIAL = "partial"
    REVIEW_REQUIRED = "review_required"


class ResponseKind(StrEnum):
    SINGLE_CHOICE = "single_choice"
    MULTI_SELECT = "multi_select"
    NUMERIC = "numeric"
    DESCRIPTIVE = "descriptive"
    UNANSWERED = "unanswered"


class MasteryLevel(StrEnum):
    UNKNOWN = "unknown"
    EMERGING = "emerging"
    DEVELOPING = "developing"
    SECURE = "secure"
    REGRESSION_FLAGGED = "regression_flagged"


class MasteryConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PerformanceMode(StrEnum):
    PRACTICE = "practice"
    SYNTHETIC_OFFICIAL = "synthetic_official"


class IssueCode(StrEnum):
    INVALID_TRANSITION = "invalid_transition"
    TENANT_MISMATCH = "tenant_mismatch"
    UNKNOWN_QUESTION = "unknown_question"
    UNKNOWN_OPTION = "unknown_option"
    DUPLICATE_RESPONSE = "duplicate_response"
    OUT_OF_SCOPE = "out_of_scope"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    SNAPSHOT_MISMATCH = "snapshot_mismatch"
    UNSUPPORTED_POLICY = "unsupported_policy"
    FINALIZATION_ROLLBACK = "finalization_rollback"
    CROSS_TENANT = "cross_tenant"
    NOT_ELIGIBLE = "not_eligible"
    REVIEW_PENDING = "review_pending"