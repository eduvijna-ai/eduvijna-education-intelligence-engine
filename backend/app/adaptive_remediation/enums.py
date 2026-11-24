"""Day 16 enumerations."""

from __future__ import annotations

from enum import StrEnum


class RemediationVerdict(StrEnum):
    NOT_READY = "NOT_READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DIAGNOSTIC_PLAN = "DIAGNOSTIC_PLAN"
    BLOCKED = "BLOCKED"


class EvidenceSupportLevel(StrEnum):
    UNKNOWN = "UNKNOWN"
    INSUFFICIENT = "INSUFFICIENT"
    SINGLE_OBSERVATION = "SINGLE_OBSERVATION"
    RECURRENT = "RECURRENT"
    SUPPORTED = "SUPPORTED"


class CorrectionPatternKind(StrEnum):
    CONCEPTUAL = "conceptual"
    FORMULA = "formula"
    CALCULATION = "calculation"
    APPLICATION = "application"
    REASONING = "reasoning"
    MISCONCEPTION = "misconception"


class RemediationStrategyKind(StrEnum):
    CONCEPT_REVIEW = "concept_review"
    FORMULA_FOCUS = "formula_focus"
    CALCULATION_DRILL = "calculation_drill"
    MISCONCEPTION_REPAIR = "misconception_repair"
    APPLICATION_PRACTICE = "application_practice"
    REASONING_PRACTICE = "reasoning_practice"
    ASSESSMENT_NEED = "assessment_need"
    REVIEW_REQUIRED = "review_required"


class PracticeStageKind(StrEnum):
    FOUNDATION = "foundation"
    APPLICATION = "application"
    TARGET_RETEST = "target_retest"


class AdaptationDecision(StrEnum):
    IMPROVE = "improve"
    CONTINUE = "continue"
    REVIEW = "review"
    REGRESS = "regress"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    STOP = "stop"


class CognitiveLevel(StrEnum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
