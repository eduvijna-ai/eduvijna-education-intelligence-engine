from __future__ import annotations

from enum import StrEnum


class Day14SourceTrustMode(StrEnum):
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    CA_ICAI_REFERENCE = "ca_icai_reference_session"
    CA_FUTURE_UNVERIFIED = "ca_future_unverified"
    IMAT_DM1005_2026 = "imat_dm1005_2026"
    IMAT_FUTURE_UNVERIFIED = "imat_future_unverified"
    EAPCET_OFFICIAL_2026 = "eapcet_official_2026"
    EAPCET_DISCOVERY_MIRROR_ONLY = "eapcet_discovery_mirror_only"


class Day14ProfileKind(StrEnum):
    SYNTHETIC_DEMO = "synthetic_demo"
    CA_SESSION_JAN2027 = "ca_session_jan2027"
    CA_FUTURE_SESSION = "ca_future_session"
    IMAT_2026 = "imat_2026"
    IMAT_FUTURE_YEAR = "imat_future_year"
    EAPCET_ENGINEERING_2026 = "eapcet_engineering_2026"
    EAPCET_AGRICULTURE_PHARMACY_2026 = "eapcet_agriculture_pharmacy_2026"


class EapcetStream(StrEnum):
    ENGINEERING = "engineering"
    AGRICULTURE_PHARMACY = "agriculture_pharmacy"


class PlanVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SHORTAGE = "shortage"
    SOURCE_PENDING = "source_pending"
    OFFICIAL_NOT_VERIFIED = "official_pattern_not_verified"
    REVIEW_REQUIRED = "review_required"
    NOT_READY = "not_ready"


class IssueCode(StrEnum):
    DAY11_DEPENDENCY_BLOCKED = "d14.governance.day11_unmerged_hold"
    DAY13_MIGRATION_0021_BLOCKER = "d14.governance.pg_0021_deferred"
    WRONG_EXAM_PACK = "d14.scope.wrong_exam_pack"
    WRONG_PAPER = "d14.scope.wrong_paper"
    WRONG_STREAM = "d14.scope.wrong_stream"
    WRONG_YEAR = "d14.scope.wrong_version_year"
    UNAPPROVED_SOURCE = "d14.source.unapproved"
    DISCOVERY_MIRROR_ONLY = "d14.source.discovery_mirror_not_authority"
    CA_FUTURE_SESSION = "d14.ca.future_session_unverified"
    CA_DESCRIPTIVE_ON_OBJECTIVE = "d14.ca.descriptive_scoring_on_objective"
    CA_RUBRIC_INVALID = "d14.ca.rubric_marks_mismatch"
    CA_ACCOUNTING_RECONCILE = "d14.ca.accounting_numeric_mismatch"
    IMAT_FUTURE_YEAR = "d14.imat.future_year_unverified"
    IMAT_COUNT_MISMATCH = "d14.imat.count_mismatch"
    IMAT_DECIMAL_SCORING = "d14.imat.scoring_precision"
    EAPCET_OFFICIAL_UNATTESTED = "d14.eapcet.official_pattern_unattested"
    EAPCET_COUNT_MISMATCH = "d14.eapcet.count_mismatch"
    EAPCET_BILINGUAL_MISMATCH = "d14.eapcet.translation_semantic_mismatch"
    TENANT_ISOLATION = "d14.scope.tenant_isolation"
    DUPLICATE_QUESTION = "d14.paper.duplicate_question"
    VALIDATION_NOT_PROVEN = "d14.validation.not_proven"
    EAPCET_SPECIFIC_BRANCH_IN_GENERIC = "d14.extensibility.forbidden_branch"
    INVALID_REQUEST_COUNT = "d14.validation.invalid_request_count"
    MISSING_TOPIC_SCOPE = "d14.scope.missing_topic"
    FINGERPRINT_TAMPER = "d14.validation.fingerprint_tamper"
    MISSING_TENANT_CONTEXT = "d14.scope.missing_tenant_context"
    ENVELOPE_ONLY_SUCCESS = "d14.persistence.envelope_only"
    SOLVER_EVIDENCE_MISSING = "d14.imat.solver_evidence_missing"
    ACADEMIC_VALIDATION_CONTAINED = "d14.containment.academic_validation_disabled"
    ISSUANCE_CONTAINED = "d14.containment.issuance_disabled"