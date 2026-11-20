"""Session-backed MCQ/multiselect/numerical verification (Issue #45 / #46 READY-01)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from app.jee_advanced.independent_solver_proof import validation_run_covers_question
from app.jee_advanced.persisted_question_loader import (
    PersistedAnswerScope,
    load_persisted_question,
)
from app.jee_advanced.stored_answer_resolution import (
    assert_scope_present,
    numerical_units_acceptable,
    question_day9_veto,
    question_type_family,
    stored_mcq_correct_keys,
    stored_numerical_spec,
    submitted_numerical_parts,
)
from app.models import Question
from app.models.enums import QuestionStatus


class VerificationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class VerificationVerdict:
    outcome: VerificationOutcome
    issue_codes: tuple[str, ...]
    demonstration_only: bool = False


def _demo_labeled(question: Question) -> bool:
    meta = question.metadata_json or {}
    return bool(meta.get("d12_core_test_fixture") or meta.get("demonstration_only"))


def _require_persisted_proof(
    session: Session,
    *,
    question: Question,
    organization_id: str,
    institution_id: str | None,
) -> tuple[bool, tuple[str, ...], bool]:
    scope_issues = assert_scope_present(organization_id, institution_id)
    if scope_issues:
        return False, scope_issues, _demo_labeled(question)
    if question_day9_veto(question):
        return False, ("day9_veto",), _demo_labeled(question)

    meta = question.metadata_json or {}
    run_id = str(meta.get("day6_validation_audit_id") or "").strip()
    if not run_id:
        return False, ("missing_validation_run_id",), _demo_labeled(question)
    ok, reason = validation_run_covers_question(
        session,
        run_id=run_id,
        question=question,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    if not ok:
        return False, (reason or "validation_proof_failed",), _demo_labeled(question)
    return True, (), _demo_labeled(question)


def _guard_question_state(question: Question) -> tuple[str, ...]:
    issues: list[str] = []
    if question.status != QuestionStatus.APPROVED.value:
        issues.append("question_not_approved")
    family = question_type_family(question)
    if family != "mcq":
        issues.append("question_type_mismatch")
    stored = stored_mcq_correct_keys(question)
    if len(stored) > 1:
        issues.append("single_choice_multiple_correct_stored")
    return tuple(issues)


def verify_persisted_mcq(
    session: Session,
    *,
    question: Question,
    organization_id: str,
    institution_id: str | None,
    selected: str | None,
) -> VerificationVerdict:
    state_issues = _guard_question_state(question)
    if state_issues:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=state_issues,
            demonstration_only=_demo_labeled(question),
        )
    proved, issues, demo = _require_persisted_proof(
        session,
        question=question,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    if not proved:
        outcome = (
            VerificationOutcome.FAIL
            if "day9_veto" in issues
            else VerificationOutcome.REVIEW_REQUIRED
        )
        return VerificationVerdict(
            outcome=outcome,
            issue_codes=issues,
            demonstration_only=demo,
        )
    if not selected:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("answer_domain_incomplete",),
            demonstration_only=demo,
        )
    stored = stored_mcq_correct_keys(question)
    if not stored:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("stored_correct_answer_missing",),
            demonstration_only=demo,
        )
    domain = {opt.option_key for opt in question.options if opt.option_key}
    if domain and selected.strip() not in domain:
        return VerificationVerdict(
            outcome=VerificationOutcome.FAIL,
            issue_codes=("selected_option_not_in_domain",),
            demonstration_only=demo,
        )
    if selected.strip() in stored:
        return VerificationVerdict(
            outcome=VerificationOutcome.PASS,
            issue_codes=(),
            demonstration_only=demo,
        )
    return VerificationVerdict(
        outcome=VerificationOutcome.FAIL,
        issue_codes=("mcq_incorrect",),
        demonstration_only=demo,
    )


def verify_persisted_multiselect(
    session: Session,
    *,
    question: Question,
    organization_id: str,
    institution_id: str | None,
    selected: frozenset[str],
) -> VerificationVerdict:
    if question.status != QuestionStatus.APPROVED.value:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("question_not_approved",),
            demonstration_only=_demo_labeled(question),
        )
    if question_type_family(question) != "multiselect":
        return VerificationVerdict(
            outcome=VerificationOutcome.FAIL,
            issue_codes=("question_type_mismatch",),
            demonstration_only=_demo_labeled(question),
        )
    proved, issues, demo = _require_persisted_proof(
        session,
        question=question,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    if not proved:
        outcome = (
            VerificationOutcome.FAIL
            if "day9_veto" in issues
            else VerificationOutcome.REVIEW_REQUIRED
        )
        return VerificationVerdict(
            outcome=outcome,
            issue_codes=issues,
            demonstration_only=demo,
        )
    if not selected:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("multiselect_domain_incomplete",),
            demonstration_only=demo,
        )
    domain = {opt.option_key for opt in question.options if opt.option_key}
    if domain:
        extra = selected - domain
        if extra:
            return VerificationVerdict(
                outcome=VerificationOutcome.FAIL,
                issue_codes=("multiselect_option_not_in_domain",),
                demonstration_only=demo,
            )
    stored = stored_mcq_correct_keys(question)
    if not stored:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("stored_correct_answer_missing",),
            demonstration_only=demo,
        )
    if selected == stored:
        return VerificationVerdict(
            outcome=VerificationOutcome.PASS,
            issue_codes=(),
            demonstration_only=demo,
        )
    return VerificationVerdict(
        outcome=VerificationOutcome.FAIL,
        issue_codes=("multiselect_mismatch",),
        demonstration_only=demo,
    )


def verify_persisted_numerical(
    session: Session,
    *,
    question: Question,
    organization_id: str,
    institution_id: str | None,
    submitted: str | None,
) -> VerificationVerdict:
    if question.status != QuestionStatus.APPROVED.value:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("question_not_approved",),
            demonstration_only=_demo_labeled(question),
        )
    if question_type_family(question) != "numerical":
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("question_type_mismatch",),
            demonstration_only=_demo_labeled(question),
        )
    proved, issues, demo = _require_persisted_proof(
        session,
        question=question,
        organization_id=organization_id,
        institution_id=institution_id,
    )
    if not proved:
        outcome = (
            VerificationOutcome.FAIL
            if "day9_veto" in issues
            else VerificationOutcome.REVIEW_REQUIRED
        )
        return VerificationVerdict(
            outcome=outcome,
            issue_codes=issues,
            demonstration_only=demo,
        )
    expected, tolerance, units_required, expected_units = stored_numerical_spec(question)
    if not submitted or expected is None:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_domain_incomplete",),
            demonstration_only=demo,
        )
    if tolerance is None or not math.isfinite(tolerance) or tolerance < 0:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_tolerance_invalid",),
            demonstration_only=demo,
        )
    units_ok, units_issue = numerical_units_acceptable(
        submitted=submitted,
        expected_units=expected_units,
        units_required=units_required,
    )
    if not units_ok:
        outcome = (
            VerificationOutcome.FAIL
            if units_issue == "numerical_units_mismatch"
            else VerificationOutcome.REVIEW_REQUIRED
        )
        return VerificationVerdict(
            outcome=outcome,
            issue_codes=(units_issue or "numerical_units_missing",),
            demonstration_only=demo,
        )
    sub_val, _ = submitted_numerical_parts(submitted)
    try:
        exp_val = float(str(expected).split()[0])
    except ValueError:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_parse_ambiguous",),
            demonstration_only=demo,
        )
    if sub_val is None:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_parse_ambiguous",),
            demonstration_only=demo,
        )
    if not math.isfinite(sub_val) or not math.isfinite(exp_val):
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_non_finite",),
            demonstration_only=demo,
        )
    if abs(sub_val - exp_val) <= tolerance:
        return VerificationVerdict(
            outcome=VerificationOutcome.PASS,
            issue_codes=(),
            demonstration_only=demo,
        )
    return VerificationVerdict(
        outcome=VerificationOutcome.FAIL,
        issue_codes=("numerical_outside_tolerance",),
        demonstration_only=demo,
    )


def verify_stored_mcq_by_id(
    session: Session,
    *,
    question_id: str,
    scope: PersistedAnswerScope,
    selected: str | None,
) -> VerificationVerdict:
    question, load_issues = load_persisted_question(session, question_id, scope)
    if load_issues:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=load_issues,
            demonstration_only=bool(
                question and _demo_labeled(question)
            ),
        )
    assert question is not None
    return verify_persisted_mcq(
        session,
        question=question,
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        selected=selected,
    )


def verify_stored_multiselect_by_id(
    session: Session,
    *,
    question_id: str,
    scope: PersistedAnswerScope,
    selected: frozenset[str],
) -> VerificationVerdict:
    scope_family = PersistedAnswerScope(
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        exam_version_id=scope.exam_version_id,
        expected_family="multiselect",
    )
    question, load_issues = load_persisted_question(session, question_id, scope_family)
    if load_issues:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=load_issues,
            demonstration_only=bool(question and _demo_labeled(question)),
        )
    assert question is not None
    return verify_persisted_multiselect(
        session,
        question=question,
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        selected=selected,
    )


def verify_stored_numerical_by_id(
    session: Session,
    *,
    question_id: str,
    scope: PersistedAnswerScope,
    submitted: str | None,
) -> VerificationVerdict:
    scope_family = PersistedAnswerScope(
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        exam_version_id=scope.exam_version_id,
        expected_family="numerical",
    )
    question, load_issues = load_persisted_question(session, question_id, scope_family)
    if load_issues:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=load_issues,
            demonstration_only=bool(question and _demo_labeled(question)),
        )
    assert question is not None
    return verify_persisted_numerical(
        session,
        question=question,
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        submitted=submitted,
    )