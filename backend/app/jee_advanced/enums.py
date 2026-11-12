from __future__ import annotations

from enum import StrEnum


class JeeAdvancedSourceTrustMode(StrEnum):
    """Distinct trust modes; never conflate synthetic with curator-approved official evidence."""

    SYNTHETIC_FIXTURE = "synthetic_fixture"
    HISTORICAL_REFERENCE_2026 = "2026_historical_reference"
    OFFICIAL_2027_NOT_VERIFIED = "2027_official_not_verified"


class AdvancedProfileKind(StrEnum):
    SYNTHETIC_DEMO = "synthetic_demo"
    REFERENCE_2026 = "reference_2026"
    CANDIDATE_2027 = "candidate_2027"


class AdvancedPlanVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SHORTAGE = "shortage"
    SOURCE_PENDING = "source_pending"
    REFERENCE_NOT_VERIFIED = "reference_profile_not_verified"
    OFFICIAL_PATTERN_NOT_VERIFIED = "official_pattern_not_verified"
    REVIEW_REQUIRED = "review_required"


class AdvancedIssueCode(StrEnum):
    DAY11_DEPENDENCY_BLOCKED = "d12.governance.day11_unmerged_hold"
    WRONG_EXAM_PACK = "d12.scope.wrong_exam_pack"
    WRONG_SUBJECT = "d12.scope.wrong_subject"
    WRONG_TOPIC = "d12.scope.wrong_topic"
    WRONG_VERSION_YEAR = "d12.scope.wrong_version_year"
    UNAPPROVED_SOURCE = "d12.source.unapproved"
    SINGLE_PAPER_ONLY = "d12.paper.single_paper_only"
    COUNT_SHORTAGE = "d12.practice.count_shortage"
    COUNT_SURPLUS = "d12.practice.count_surplus"
    UNVALIDATED_QUESTION = "d12.practice.unvalidated_question"
    OFF_TOPIC_FILLER = "d12.practice.off_topic_filler"
    JEE_MAIN_FALLBACK = "d12.scope.jee_main_fallback_blocked"
    TENANT_ISOLATION = "d12.scope.tenant_isolation"
    DUPLICATE_CROSS_PAPER = "d12.paper.duplicate_cross_paper"
    BLUEPRINT_UNPINNED = "d12.blueprint.unpinned_counts"
    TRUST_PROFILE_MISMATCH = "d12.trust.profile_mismatch"
    INVALID_PAPER_CODE = "d12.paper.invalid_paper_code"
    DUPLICATE_PAPER_CODE = "d12.paper.duplicate_paper_code"
    EMPTY_PAPER_PLAN = "d12.paper.empty_plan"
    PAPER_QUOTA_SHORTAGE = "d12.paper.quota_shortage"
    MALFORMED_SCORING_RULE = "d12.scoring.malformed_rule"
    INVALID_REQUESTED_COUNT = "d12.paper.invalid_requested_count"
    COUNT_SURPLUS_REJECTED = "d12.paper.count_surplus"
