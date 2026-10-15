from __future__ import annotations

from typing import Any

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DiagnosticQuestionItem,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.enums import DEFAULT_TAXONOMY_VERSION, DiagnosticValidationStatus


def parse_model_diagnostic_payload(
    item: DiagnosticQuestionItem,
    payload: dict[str, Any],
    *,
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION,
) -> DistractorDiagnosticResult:
    raw_tags = payload.get("option_tags") or []
    tags: list[OptionDiagnosticTag] = []
    option_map = {o.option_key: o for o in item.options}
    for raw in raw_tags:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("option_key", ""))
        option = option_map.get(key)
        is_correct = bool(option.is_correct) if option else bool(raw.get("is_correct"))
        tags.append(
            OptionDiagnosticTag(
                item_id=item.item_id,
                option_key=key,
                is_correct=is_correct,
                misconception_code=raw.get("misconception_code"),
                diagnostic_signal=raw.get("diagnostic_signal"),
                error_pattern=raw.get("error_pattern"),
                evidence_refs=list(raw.get("evidence_refs") or []),
                confidence=raw.get("confidence"),
                taxonomy_version=str(raw.get("taxonomy_version") or taxonomy_version),
                metadata_json={"option_text": option.text if option else ""},
            )
        )
    for option in item.options:
        if any(t.option_key == option.option_key for t in tags):
            continue
        tags.append(
            OptionDiagnosticTag(
                item_id=item.item_id,
                option_key=option.option_key,
                is_correct=option.is_correct,
                taxonomy_version=taxonomy_version,
                metadata_json={"option_text": option.text},
            )
        )
    return DistractorDiagnosticResult(
        item_id=item.item_id,
        question_type=item.question_type,
        option_tags=tags,
        taxonomy_version=taxonomy_version,
        source_revision_ids=list(item.source_revision_ids),
        aggregate_status=DiagnosticValidationStatus.PASS,
    )


def build_gateway_user_payload(request: DiagnosticAuthoringRequest) -> dict[str, Any]:
    from app.diagnostic_intelligence.candidate_resolver import resolve_misconception_candidates

    candidates = resolve_misconception_candidates(request)
    return {
        "item_id": request.item.item_id,
        "stem_text": request.item.stem_text,
        "options": [o.model_dump(mode="json") for o in request.item.options],
        "taxonomy_version": request.taxonomy_version,
        "misconception_candidates": [
            {
                "misconception_code": c.misconception_code,
                "diagnostic_signal": c.diagnostic_signal,
                "error_pattern": c.error_pattern,
            }
            for c in candidates
        ],
        "allowed_source_revision_ids": request.allowed_source_revision_ids,
        "allowed_evidence_refs": request.allowed_evidence_refs,
        "fixture_scenario": request.fixture_scenario,
        "run_id": request.item.metadata_json.get("run_id"),
    }
