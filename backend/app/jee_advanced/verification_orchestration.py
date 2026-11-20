"""Day8/10 orchestration and independent verifiers for JEE Advanced (D12-26…31)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.orchestration.gateway.protocol import GenerationGateway


class VerificationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class VerificationVerdict:
    outcome: VerificationOutcome
    issue_codes: tuple[str, ...]
    demonstration_only: bool = False


def cognitive_competency_review(
    *,
    item_count: int,
    marks_total: float,
    cognitive_weights: dict[str, float] | None,
) -> VerificationVerdict:
    """D12-26: weighted cognitive/competency veto when evidence is missing."""

    if item_count <= 0 or marks_total <= 0:
        return VerificationVerdict(
            outcome=VerificationOutcome.FAIL,
            issue_codes=("empty_paper_plan",),
        )
    if not cognitive_weights:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("cognitive_weights_missing",),
        )
    return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=())


def generation_gateway_protocol() -> type[GenerationGateway]:
    """D12-27: production must use AnythingLLM adapter boundary only."""

    return GenerationGateway


def verify_mcq_answer(
    *,
    selected: str | None,
    correct: str | None,
    independent_solver_evidence: dict[str, Any] | None,
) -> VerificationVerdict:
    """D12-28: bind correctness to persisted independent solver rows."""

    if independent_solver_evidence is None:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("independent_solver_not_persisted",),
        )
    if str(independent_solver_evidence.get("kind") or "") != "independent_solver":
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("independent_solver_kind_mismatch",),
        )
    if not selected or not correct:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("answer_domain_incomplete",),
        )
    if selected.strip() == correct.strip():
        return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=())
    return VerificationVerdict(outcome=VerificationOutcome.FAIL, issue_codes=("mcq_incorrect",))


def verify_multiselect_answer(
    *,
    selected: frozenset[str],
    correct: frozenset[str],
    independent_solver_evidence: dict[str, Any] | None,
) -> VerificationVerdict:
    base = verify_mcq_answer(
        selected=next(iter(selected), None) if selected else None,
        correct=next(iter(correct), None) if correct else None,
        independent_solver_evidence=independent_solver_evidence,
    )
    if base.outcome != VerificationOutcome.PASS:
        return base
    if selected == correct:
        return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=())
    return VerificationVerdict(
        outcome=VerificationOutcome.FAIL,
        issue_codes=("multiselect_mismatch",),
    )


def verify_numerical_answer(
    *,
    submitted: str | None,
    expected: str | None,
    tolerance: float | None,
    units_required: bool,
    independent_solver_evidence: dict[str, Any] | None,
) -> VerificationVerdict:
    """D12-29: units/tolerance/LaTeX ambiguity routes to REVIEW."""

    if independent_solver_evidence is None:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("independent_solver_not_persisted",),
        )
    if not submitted or not expected:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_domain_incomplete",),
        )
    if tolerance is None or (units_required and "(" not in submitted and "[" not in submitted):
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_policy_unverified",),
        )
    try:
        diff = abs(float(submitted) - float(expected))
    except ValueError:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_parse_ambiguous",),
        )
    if diff <= tolerance:
        return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=())
    return VerificationVerdict(
        outcome=VerificationOutcome.FAIL,
        issue_codes=("numerical_outside_tolerance",),
    )


def verify_stem_assets(
    *,
    latex: str | None,
    has_image: bool,
    alt_text: str | None,
) -> VerificationVerdict:
    """D12-30: broken STEM assets require human review."""

    issues: list[str] = []
    if latex and ("$$" in latex and latex.count("$") < 4):
        issues.append("latex_unbalanced")
    if has_image and not (alt_text or "").strip():
        issues.append("image_alt_text_missing")
    if issues:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=tuple(issues),
        )
    return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=())


def bounded_repair_allowed(*, repairs_used: int, repair_budget: int = 2) -> VerificationVerdict:
    """D12-31: cap orchestration repairs (Day8 bounded repair policy)."""

    if repairs_used > repair_budget:
        return VerificationVerdict(
            outcome=VerificationOutcome.FAIL,
            issue_codes=("repair_budget_exceeded",),
        )
    return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=())