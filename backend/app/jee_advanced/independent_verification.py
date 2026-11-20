"""Session-backed MCQ/multiselect/numerical verification (Issue #45 / #46 READY-01)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from app.jee_advanced.independent_solver_proof import validation_run_covers_question
from app.jee_advanced.stored_answer_resolution import (
    assert_scope_present,
    question_day9_veto,
    stored_mcq_correct_keys,
    stored_numerical_spec,
)
from app.models import Question


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


def verify_persisted_mcq(
    session: Session,
    *,
    question: Question,
    organization_id: str,
    institution_id: str | None,
    selected: str | None,
) -> VerificationVerdict:
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
    expected, tolerance, units_required = stored_numerical_spec(question)
    if not submitted or not expected:
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
    if units_required and not re.search(r"\b[a-zA-Z]", submitted):
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_units_missing",),
            demonstration_only=demo,
        )
    try:
        sub_val = float(submitted.split()[0])
        exp_val = float(expected.split()[0])
    except ValueError:
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