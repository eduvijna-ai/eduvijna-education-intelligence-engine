from __future__ import annotations

from enum import StrEnum


class OrchestrationRunStatus(StrEnum):
    PLANNING = "planning"
    AUTHORING = "authoring"
    SOLVING = "solving"
    REVIEWING = "reviewing"
    REPAIRING = "repairing"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewVerdictStatus(StrEnum):
    PASS = "pass"
    REPAIR = "repair"
    REJECT = "reject"
    REVIEW_REQUIRED = "review_required"


class GenerationNodeRole(StrEnum):
    AUTHOR = "author"
    SOLVER = "solver"
    PATTERN_REVIEW = "pattern_review"
    CURRICULUM_REVIEW = "curriculum_review"
    EDUCATIONAL_REVIEW = "educational_review"
    REPAIR = "repair"


class OrchestrationErrorCode(StrEnum):
    GATEWAY_TIMEOUT = "gateway_timeout"
    GATEWAY_UNAUTHORIZED = "gateway_unauthorized"
    GATEWAY_UNAVAILABLE = "gateway_unavailable"
    GATEWAY_INVALID_JSON = "gateway_invalid_json"
    VALIDATION_REJECT = "validation_reject"
    TENANT_ISOLATION = "tenant_isolation"
    PROVENANCE_REJECT = "provenance_reject"
    DUPLICATE_REJECT = "duplicate_reject"
    REPAIR_EXHAUSTED = "repair_exhausted"
    NODE_EXCEPTION = "node_exception"
    IDEMPOTENT_REPLAY = "idempotent_replay"


HARD_MAX_REPAIRS = 5
