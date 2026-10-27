from __future__ import annotations

from enum import StrEnum


class RootCauseVerdictStatus(StrEnum):
    PASS = "pass"
    REVIEW_REQUIRED = "review_required"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    FAIL = "fail"


class RootCauseIssueCode(StrEnum):
    CORRECT_OPTION_TAGGED = "d10.root.correct_option_tagged"
    DAY6_BLOCKING = "d10.root.day6_blocking"
    DAY9_TAG_REJECTED = "d10.root.day9_tag_rejected"
    UNKNOWN_MISCONCEPTION = "d10.root.unknown_misconception"
    INACTIVE_TAXONOMY = "d10.root.inactive_taxonomy"
    MISSING_GRAPH = "d10.root.missing_graph"
    MISSING_CONCEPT = "d10.root.missing_concept"
    FOREIGN_TENANT = "d10.root.foreign_tenant"
    UNAUTHORIZED_SOURCE = "d10.root.unauthorized_source"
    NO_PREREQUISITE_PATH = "d10.root.no_prerequisite_path"
    AMBIGUOUS_PATH = "d10.root.ambiguous_path"
    CONFLICTING_EVIDENCE = "d10.root.conflicting_evidence"
    PATH_BUDGET_EXHAUSTED = "d10.root.path_budget_exhausted"
    UNTRUSTED_TAG_VALIDATION = "d10.root.untrusted_tag_validation"
    SNAPSHOT_ALLOWLIST_SPOOF = "d10.root.snapshot_allowlist_spoof"


DEFAULT_ROOT_CAUSE_MAPPING_VERSION = "root-cause-mapping@v1"
