from __future__ import annotations

from enum import StrEnum


class ValidationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    NOT_APPLICABLE = "not_applicable"
    REVIEW_REQUIRED = "review_required"


class ValidationSeverity(StrEnum):
    INFO = "info"
    ADVISORY = "advisory"
    MANDATORY = "mandatory"
    SAFETY = "safety"


class EvidenceAuthority(StrEnum):
    OFFICIAL_CURRICULUM_RULE = "official_curriculum_rule"
    OFFICIAL_ASSESSMENT_EVIDENCE = "official_assessment_evidence"
    COMPETITIVE_DERIVED = "competitive_derived"
    INSTITUTION_PREFERENCE = "institution_preference"
    TEACHER_PREFERENCE = "teacher_preference"


class PolicyAuthorityTier(StrEnum):
    GLOBAL = "global"
    COUNTRY_BOARD = "country_board"
    INSTITUTION = "institution"
    TEACHER = "teacher"
