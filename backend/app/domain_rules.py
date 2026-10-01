from __future__ import annotations

from datetime import date
from typing import Iterable

from app.models.enums import PolicyScopeType
from app.schemas.domain import DiagnosticTaxonomyInput, PolicyRuleInput, QuestionInput

OFFICIAL_SCOPES = {
    PolicyScopeType.COUNTRY,
    PolicyScopeType.BOARD,
    PolicyScopeType.EXAM,
}
SCOPE_PRECEDENCE = {
    PolicyScopeType.COUNTRY: 100,
    PolicyScopeType.BOARD: 200,
    PolicyScopeType.EXAM: 300,
    PolicyScopeType.INSTITUTION: 400,
    PolicyScopeType.TEACHER: 500,
}


class PolicyConflictError(ValueError):
    pass


def validate_question_diagnostic_references(
    question: QuestionInput,
    taxonomy_entries: Iterable[DiagnosticTaxonomyInput],
) -> None:
    entries = list(taxonomy_entries)
    by_id = {entry.id: entry for entry in entries}
    by_code = {entry.code: entry for entry in entries}
    if len(by_id) != len(entries) or len(by_code) != len(entries):
        raise ValueError("diagnostic taxonomy ids and codes must be unique")

    for option in question.options:
        entry = None
        if option.diagnostic_taxonomy_entry_id is not None:
            entry = by_id.get(option.diagnostic_taxonomy_entry_id)
            if entry is None:
                raise ValueError("question option references unknown diagnostic taxonomy entry")
        if option.error_code is not None:
            code_entry = by_code.get(option.error_code)
            if code_entry is None:
                raise ValueError("question option error_code is not defined in diagnostic taxonomy")
            if entry is not None and code_entry.id != entry.id:
                raise ValueError("question option diagnostic entry and error_code disagree")


def resolve_policy_rule(
    rules: Iterable[PolicyRuleInput],
    policy_key: str,
    *,
    on_date: date | None = None,
) -> PolicyRuleInput | None:
    effective_date = on_date or date.today()
    candidates = [
        rule
        for rule in rules
        if rule.policy_key == policy_key
        and rule.active
        and (rule.effective_from is None or rule.effective_from <= effective_date)
        and (rule.effective_to is None or rule.effective_to >= effective_date)
    ]
    if not candidates:
        return None

    hard_official = [
        rule
        for rule in candidates
        if rule.scope_type in OFFICIAL_SCOPES
        and rule.metadata_json.get("enforcement") == "hard"
    ]
    pool = hard_official or candidates
    best_priority = max(rule.priority for rule in pool)
    pool = [rule for rule in pool if rule.priority == best_priority]
    best_scope = max(SCOPE_PRECEDENCE[rule.scope_type] for rule in pool)
    finalists = [rule for rule in pool if SCOPE_PRECEDENCE[rule.scope_type] == best_scope]

    canonical_values = {repr(sorted(rule.value_json.items())) for rule in finalists}
    if len(canonical_values) > 1:
        raise PolicyConflictError(
            f"conflicting policy rules for {policy_key!r} at the same precedence"
        )

    return sorted(finalists, key=lambda rule: rule.scope_code)[0]
