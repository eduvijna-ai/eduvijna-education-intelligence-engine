from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.orchestration.contracts import DraftQuestionItem, ReviewVerdict, SolverResult


class RepairPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repair_instructions: dict[str, list[str]] = Field(default_factory=dict)


class DiagnosticOptionTagOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    misconception_code: str | None = None
    diagnostic_signal: str | None = None
    error_pattern: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_correct: bool | None = None


class DiagnosticEnrichmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    option_tags: list[DiagnosticOptionTagOutput] = Field(default_factory=list)


class GenerationOutputValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_generation_output(schema_name: str, parsed: dict[str, Any]) -> dict[str, Any]:
    try:
        if schema_name == "DraftQuestionItem":
            return DraftQuestionItem.model_validate(parsed).model_dump(mode="json")
        if schema_name == "SolverResult":
            return SolverResult.model_validate(parsed).model_dump(mode="json")
        if schema_name == "ReviewVerdict":
            return ReviewVerdict.model_validate(parsed).model_dump(mode="json")
        if schema_name == "RepairPlan":
            return RepairPlan.model_validate(parsed).model_dump(mode="json")
        if schema_name == "DiagnosticEnrichmentOutput":
            return DiagnosticEnrichmentOutput.model_validate(parsed).model_dump(mode="json")
    except ValidationError as exc:
        raise GenerationOutputValidationError("model_schema_invalid", str(exc)) from exc
    raise GenerationOutputValidationError(
        "model_schema_unknown", f"Unsupported output schema: {schema_name}"
    )
