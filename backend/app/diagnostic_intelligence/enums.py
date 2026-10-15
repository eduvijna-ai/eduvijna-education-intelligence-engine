from __future__ import annotations

from enum import StrEnum


class MisconceptionStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class DiagnosticValidationStatus(StrEnum):
    PASS = "pass"
    REPAIR = "repair"
    REJECT = "reject"
    REVIEW_REQUIRED = "review_required"
    NOT_APPLICABLE = "not_applicable"


class DiagnosticIssueCode(StrEnum):
    UNKNOWN_MISCONCEPTION_CODE = "unknown_misconception_code"
    INACTIVE_MISCONCEPTION = "inactive_misconception"
    CURRICULUM_SCOPE_MISMATCH = "curriculum_scope_mismatch"
    CORRECT_OPTION_MISLABELED = "correct_option_mislabeled"
    DUPLICATE_MISCONCEPTION = "duplicate_misconception"
    REDUNDANT_DISTRACTOR = "redundant_distractor"
    NONSENSICAL_DISTRACTOR = "nonsensical_distractor"
    SECOND_CORRECT_DISTRACTOR = "second_correct_distractor"
    SIGNAL_TEXT_MISMATCH = "signal_text_mismatch"
    FORGED_EVIDENCE_REF = "forged_evidence_ref"
    TENANT_EVIDENCE_MISMATCH = "tenant_evidence_mismatch"
    DAY6_BLOCKING = "day6_blocking"
    MALFORMED_MODEL_OUTPUT = "malformed_model_output"
    MISSING_DIAGNOSTIC_TAG = "missing_diagnostic_tag"
    UNSUPPORTED_QUESTION_TYPE = "unsupported_question_type"


DEFAULT_TAXONOMY_VERSION = "misconception-taxonomy@v1"
