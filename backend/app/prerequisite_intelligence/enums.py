from __future__ import annotations

from enum import StrEnum


class GraphLifecycleStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DRAFT = "draft"


class EdgeProvenanceClass(StrEnum):
    OFFICIAL = "official"
    SYNTHETIC = "synthetic"
    INFERRED = "inferred"


class GraphIssueCode(StrEnum):
    UNKNOWN_NODE = "d10.graph.unknown_node"
    DUPLICATE_EDGE = "d10.graph.duplicate_edge"
    SELF_EDGE = "d10.graph.self_edge"
    INVALID_WEIGHT = "d10.graph.invalid_weight"
    CYCLE_DETECTED = "d10.graph.cycle_detected"
    MISSING_PROVENANCE = "d10.graph.missing_provenance"
    UNAUTHORIZED_PROVENANCE = "d10.graph.unauthorized_provenance"
    CROSS_SUBJECT_EDGE = "d10.graph.cross_subject_edge"
    CROSS_VERSION_EDGE = "d10.graph.cross_version_edge"
    GRADE_PROGRESSION_UNSUPPORTED = "d10.graph.grade_progression_unsupported"
    FOREIGN_TENANT = "d10.graph.foreign_tenant"
    STALE_CURRICULUM_VERSION = "d10.graph.stale_curriculum_version"
    DISCONNECTED_CONCEPT = "d10.graph.disconnected_concept"
    CONFLICTING_EVIDENCE = "d10.graph.conflicting_evidence"
    PATH_BUDGET_EXHAUSTED = "d10.graph.path_budget_exhausted"
    DEPTH_LIMIT_EXCEEDED = "d10.graph.depth_limit_exceeded"


class GraphAuditStatus(StrEnum):
    PASS = "pass"
    REVIEW_REQUIRED = "review_required"
    FAIL = "fail"
