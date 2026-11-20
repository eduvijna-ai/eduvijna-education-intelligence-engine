"""Resolve canonical correct answers from persisted Question rows (READY-01)."""

from __future__ import annotations

from app.models import Question
from app.models.enums import QuestionType


def stored_mcq_correct_keys(question: Question) -> frozenset[str]:
    keys = {opt.option_key for opt in question.options if opt.is_correct and opt.option_key}
    if keys:
        return frozenset(keys)
    answer = question.answer_json or {}
    key = str(answer.get("option_key") or "").strip()
    return frozenset({key}) if key else frozenset()


def stored_numerical_spec(
    question: Question,
) -> tuple[str | None, float | None, bool, str | None]:
    answer = question.answer_json or {}
    rubric = question.rubric_json or {}
    value = answer.get("value")
    if value is None:
        value = answer.get("numerical_answer")
    expected = str(value).strip() if value is not None else None
    tol_raw = rubric.get("tolerance")
    if tol_raw is None:
        tol_raw = rubric.get("numerical_tolerance")
    tolerance: float | None = None
    if tol_raw is not None:
        try:
            tolerance = float(tol_raw)
        except (TypeError, ValueError):
            tolerance = None
    units_required = bool(rubric.get("units_required") or answer.get("units_required"))
    expected_units = str(
        answer.get("units") or rubric.get("expected_units") or answer.get("unit") or ""
    ).strip().lower() or None
    return expected, tolerance, units_required, expected_units


def submitted_numerical_parts(submitted: str) -> tuple[float | None, str | None]:
    parts = submitted.strip().split(maxsplit=1)
    try:
        value = float(parts[0])
    except (ValueError, IndexError):
        return None, None
    units = parts[1].strip().lower() if len(parts) > 1 else None
    return value, units


def numerical_units_acceptable(
    *,
    submitted: str,
    expected_units: str | None,
    units_required: bool,
) -> tuple[bool, str | None]:
    if not units_required:
        return True, None
    if not expected_units:
        return False, "numerical_expected_units_missing"
    _, sub_units = submitted_numerical_parts(submitted)
    if not sub_units:
        return False, "numerical_units_missing"
    if sub_units != expected_units:
        return False, "numerical_units_mismatch"
    return True, None


def selected_in_option_domain(question: Question, selected: str) -> bool:
    domain = {opt.option_key for opt in question.options if opt.option_key}
    return selected.strip() in domain if domain else False


def assert_scope_present(organization_id: str, institution_id: str | None) -> tuple[str, ...]:
    issues: list[str] = []
    if not (organization_id or "").strip():
        issues.append("organization_scope_missing")
    if institution_id is not None and not str(institution_id).strip():
        issues.append("institution_scope_missing")
    return tuple(issues)


def question_day9_veto(question: Question) -> bool:
    return bool((question.metadata_json or {}).get("day9_veto"))


def question_type_family(question: Question) -> str:
    qtype = str(question.question_type or "").lower()
    if qtype in {QuestionType.SINGLE_CHOICE.value, "mcq"}:
        return "mcq"
    if qtype == QuestionType.MULTIPLE_CHOICE.value:
        return "multiselect"
    if qtype in {"numerical", "numeric", "numerical_answer"}:
        return "numerical"
    return qtype or "unknown"