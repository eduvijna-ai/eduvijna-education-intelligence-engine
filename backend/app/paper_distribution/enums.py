from __future__ import annotations

from enum import StrEnum


class MultiLabelPolicy(StrEnum):
    PRIMARY_ONLY = "primary_only"
    FRACTIONAL_SPLIT = "fractional_split"


class DistributionDimensionStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"
    INFEASIBLE = "infeasible"


class PaperDistributionIssueCode(StrEnum):
    DUPLICATE_ITEM_ID = "d10.paper.duplicate_item_id"
    MISSING_COGNITIVE = "d10.paper.missing_cognitive"
    MISSING_COMPETENCY = "d10.paper.missing_competency"
    INVALID_COGNITIVE = "d10.paper.invalid_cognitive"
    INVALID_COMPETENCY = "d10.paper.invalid_competency"
    CREATE_LEVEL_REJECTED = "d10.paper.create_level_rejected"
    INVALID_MARKS = "d10.paper.invalid_marks"
    ZERO_MARKS = "d10.paper.zero_marks"
    NEGATIVE_MARKS = "d10.paper.negative_marks"
    UNSUPPORTED_TAXONOMY = "d10.paper.unsupported_taxonomy"
    TARGET_INFEASIBLE = "d10.paper.target_infeasible"
    TARGET_MISMATCH = "d10.paper.target_mismatch"
    COUNT_MARK_DISAGREEMENT = "d10.paper.count_mark_disagreement"
    MULTI_LABEL_DOUBLE_COUNT = "d10.paper.multi_label_double_count"
    EMPTY_PAPER = "d10.paper.empty_paper"
    OVERFLOW_TOTAL = "d10.paper.overflow_total"
    MALFORMED_TARGET_DIMENSION = "d10.paper.malformed_target_dimension"
    NON_FINITE_MARKS = "d10.paper.non_finite_marks"
    DUPLICATE_COMPETENCY_LABEL = "d10.paper.duplicate_competency_label"


class PaperDistributionVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"
