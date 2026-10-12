from __future__ import annotations

from app.education_intelligence.contracts import ValidationResult
from app.education_intelligence.enums import ValidationStatus


def explain_result(result: ValidationResult) -> str:
    codes = ", ".join(result.rule_codes) if result.rule_codes else "none"
    refs = []
    for ev in result.evidence:
        refs.append(f"{ev.authority.value}:{ev.entity_type}:{ev.entity_id or '-'}")
    ref_text = "; ".join(refs) if refs else "structured evidence only"
    return (
        f"[{result.validator_id}@{result.validator_version}] "
        f"status={result.status.value} rules={codes} "
        f"blocking={result.blocking} evidence={ref_text}"
    )


def explain_results(results: list[ValidationResult]) -> list[str]:
    lines = [explain_result(r) for r in results if r.status != ValidationStatus.NOT_APPLICABLE]
    if not any("LLM" in line or "AI review" in line for line in lines):
        lines.append("No LLM or AI review was performed for this validation run.")
    return lines
