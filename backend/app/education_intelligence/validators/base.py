from __future__ import annotations

from typing import Protocol

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.contracts import CanonicalAssessmentItem, ValidationResult


class ItemValidator(Protocol):
    validator_id: str
    validator_version: str

    def validate(
        self, item: CanonicalAssessmentItem, ctx: ValidationContext
    ) -> ValidationResult: ...


class ProgressionValidator(Protocol):
    validator_id: str
    validator_version: str

    def validate_progression(
        self, progression: list[str], ctx: ValidationContext
    ) -> ValidationResult: ...
