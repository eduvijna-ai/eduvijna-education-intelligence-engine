from __future__ import annotations

from enum import StrEnum


class CuetClatSourceTrustMode(StrEnum):
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    CUET_HISTORICAL_2026 = "cuet_2026_historical_reference"
    CUET_2027_NOT_VERIFIED = "cuet_2027_not_verified"
    CLAT_OFFICIAL_2027 = "clat_2027_official_source_attested"


class CuetClatProfileKind(StrEnum):
    SYNTHETIC_DEMO = "synthetic_demo"
    CUET_REFERENCE_2026 = "cuet_reference_2026"
    CUET_CANDIDATE_2027 = "cuet_candidate_2027"
    CLAT_2027 = "clat_2027"


class PlanVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SHORTAGE = "shortage"
    SOURCE_PENDING = "source_pending"
    OFFICIAL_NOT_VERIFIED = "official_pattern_not_verified"
    REVIEW_REQUIRED = "review_required"
    NOT_READY = "not_ready"


class IssueCode(StrEnum):
    DAY11_DEPENDENCY_BLOCKED = "d13.governance.day11_unmerged_hold"
    WRONG_EXAM_PACK = "d13.scope.wrong_exam_pack"
    WRONG_SUBJECT = "d13.scope.wrong_subject"
    WRONG_MEDIUM = "d13.scope.wrong_medium"
    WRONG_YEAR = "d13.scope.wrong_version_year"
    UNAPPROVED_SOURCE = "d13.source.unapproved"
    CUET_2027_UNVERIFIED = "d13.cuet.2027_not_verified"
    CUET_COUNT_MISMATCH = "d13.cuet.count_mismatch"
    CUET_TEST_LIMIT = "d13.cuet.test_selection_limit"
    CLAT_COUNT_MISMATCH = "d13.clat.count_mismatch"
    CLAT_RANGE_INFEASIBLE = "d13.clat.section_range_infeasible"
    CLAT_SECTION_OVERRIDE_INVALID = "d13.clat.section_override_invalid"
    TENANT_ISOLATION = "d13.scope.tenant_isolation"
    STALE_REPLAY = "d13.replay.stale_binding"
    DUPLICATE_QUESTION = "d13.paper.duplicate_question"
    PASSAGE_ANSWER_MISMATCH = "d13.clat.passage_answer_mismatch"
    FORGED_CITATION = "d13.rag.forged_citation"
    STALE_CURRENT_AFFAIRS = "d13.rag.stale_news"
    JEE_MAIN_FALLBACK = "d13.scope.jee_main_fallback_blocked"
    COPYRIGHT_VIOLATION = "d13.content.copyright_violation"