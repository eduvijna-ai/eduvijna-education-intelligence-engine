from __future__ import annotations

from enum import StrEnum


class PaperPlanMode(StrEnum):
    PRACTICE_EXACT_COUNT = "practice_exact_count"
    OFFICIAL_PATTERN_REPLICA = "official_pattern_replica"


class PaperPlanVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"
    INFEASIBLE = "infeasible"


class OfficialPatternAuthorityStatus(StrEnum):
    """Whether NTA bulletin/syllabus are approved for hard official replica rules."""

    NOT_VERIFIED = "not_verified"
    OFFICIAL_PATTERN_NOT_VERIFIED = "official_pattern_not_verified"
    VERIFIED = "verified"


class JeeMainSubjectCode(StrEnum):
    MATHEMATICS = "mathematics"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"


class JeeMainSectionCode(StrEnum):
    SECTION_A = "section_a"
    SECTION_B = "section_b"


class JeeMainQuestionTypeQuota(StrEnum):
    MCQ = "mcq"
    NUMERICAL = "numerical"


class SyllabusTopicKind(StrEnum):
    OFFICIAL_NTA_UNIT = "official_nta_unit"
    DERIVED_EDUVIJNA_GROUP = "derived_eduvijna_group"


class PaperPlanIssueCode(StrEnum):
    OFFICIAL_SOURCE_NOT_VERIFIED = "official_source_not_verified"
    OFFICIAL_SOURCE_STALE = "official_source_stale"
    OFFICIAL_SOURCE_TAMPERED = "official_source_tampered"
    UNKNOWN_SUBJECT = "unknown_subject"
    UNKNOWN_TOPIC = "unknown_topic"
    OUT_OF_SYLLABUS = "out_of_syllabus"
    STALE_EXAM_VERSION = "stale_exam_version"
    WRONG_TENANT = "wrong_tenant"
    COUNT_MISMATCH = "count_mismatch"
    INSUFFICIENT_VALIDATED_POOL = "insufficient_validated_pool"
    OFF_TOPIC_FILLER = "off_topic_filler"
    DUPLICATE_ITEM_ID = "duplicate_item_id"
    IMPOSSIBLE_QUOTA = "impossible_quota"
    UNAPPROVED_OFFICIAL_POLICY = "unapproved_official_policy"
    INVALID_ANSWER = "invalid_answer"
    INVALID_MARKS = "invalid_marks"
    REPLAY_IDEMPOTENCY_CONFLICT = "replay_idempotency_conflict"
    FOREIGN_TENANT_CONTENT = "foreign_tenant_content"
    INVENTED_NTA_QUOTA = "invented_nta_quota"
