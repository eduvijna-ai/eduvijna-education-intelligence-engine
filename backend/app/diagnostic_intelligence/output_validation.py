from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.diagnostic_intelligence.contracts import DiagnosticQuestionItem, OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION


class DiagnosticOutputValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DiagnosticOptionTagOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_key: str
    misconception_code: str | None = None
    diagnostic_signal: str | None = None
    error_pattern: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_correct: bool | None = None


class DiagnosticEnrichmentGatewayOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    option_tags: list[DiagnosticOptionTagOutput]


def parse_strict_diagnostic_output(
    item: DiagnosticQuestionItem,
    payload: dict[str, Any],
    *,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
) -> list[OptionDiagnosticTag]:
    try:
        parsed = DiagnosticEnrichmentGatewayOutput.model_validate(payload)
    except ValidationError as exc:
        raise DiagnosticOutputValidationError("model_schema_invalid", str(exc)) from exc

    if parsed.item_id != item.item_id:
        raise DiagnosticOutputValidationError(
            "model_schema_invalid",
            f"item_id mismatch: expected {item.item_id}, got {parsed.item_id}",
        )

    expected_keys = {o.option_key for o in item.options}
    seen: set[str] = set()
    option_map = {o.option_key: o for o in item.options}
    tags: list[OptionDiagnosticTag] = []

    for raw in parsed.option_tags:
        if raw.option_key in seen:
            raise DiagnosticOutputValidationError(
                "model_schema_invalid",
                f"duplicate option_key: {raw.option_key}",
            )
        seen.add(raw.option_key)
        if raw.option_key not in expected_keys:
            raise DiagnosticOutputValidationError(
                "model_schema_invalid",
                f"unknown option_key: {raw.option_key}",
            )
        canonical = option_map[raw.option_key]
        if raw.is_correct is not None and raw.is_correct != canonical.is_correct:
            raise DiagnosticOutputValidationError(
                "model_schema_invalid",
                f"contradictory correctness for {raw.option_key}",
            )
        tags.append(
            OptionDiagnosticTag(
                item_id=item.item_id,
                option_key=raw.option_key,
                is_correct=canonical.is_correct,
                misconception_code=raw.misconception_code,
                diagnostic_signal=raw.diagnostic_signal,
                error_pattern=raw.error_pattern,
                evidence_refs=list(raw.evidence_refs),
                confidence=raw.confidence,
                taxonomy_version=taxonomy_version,
                metadata_json={"option_text": canonical.text},
            )
        )

    if seen != expected_keys:
        missing = sorted(expected_keys - seen)
        extra = sorted(seen - expected_keys)
        raise DiagnosticOutputValidationError(
            "model_schema_invalid",
            f"option key mismatch missing={missing} extra={extra}",
        )

    return tags
