"""Day8/10 orchestration and independent verifiers for JEE Advanced (D12-26…31)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.jee_advanced.independent_verification import (
    VerificationOutcome,
    VerificationVerdict,
    verify_persisted_mcq,
)
from app.models import Question
from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationRequest


def cognitive_competency_review(
    *,
    questions: tuple[Question, ...],
    marks_by_question_id: dict[str, float],
) -> VerificationVerdict:
    """D12-26: question-bound cognitive weights; missing metadata → REVIEW."""

    if not questions or sum(marks_by_question_id.values()) <= 0:
        return VerificationVerdict(
            outcome=VerificationOutcome.FAIL,
            issue_codes=("empty_paper_plan",),
        )
    missing = 0
    for q in questions:
        meta = q.metadata_json or {}
        weights = meta.get("cognitive_weights")
        if not isinstance(weights, dict) or not weights:
            missing += 1
    if missing:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("cognitive_weights_missing", f"missing_count:{missing}"),
        )
    return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=())


def run_scoped_generation_probe(
    *,
    item_id: str,
    run_id: str,
) -> tuple[VerificationVerdict, int]:
    """D12-27: execute Day8 FakeGenerationGateway author→solver chain (not a type export)."""

    gateway = FakeGenerationGateway()
    author_req = GenerationRequest(
        role=GenerationNodeRole.AUTHOR,
        prompt_version="jee-adv-probe@v1",
        system_prompt="author",
        user_payload={"item_id": item_id, "run_id": run_id, "allowed_source_revision_ids": []},
        output_schema_name="author_item_v1",
        scenario="clean_pass",
    )
    author_resp = gateway.generate(author_req)
    solver_req = GenerationRequest(
        role=GenerationNodeRole.SOLVER,
        prompt_version="jee-adv-probe@v1",
        system_prompt="solver",
        user_payload={"item_id": item_id, "run_id": run_id, "stem": author_resp.parsed},
        output_schema_name="solver_item_v1",
        scenario="clean_pass",
    )
    gateway.generate(solver_req)
    calls = len(gateway.call_history())
    if not author_resp.raw_text:
        return (
            VerificationVerdict(
                outcome=VerificationOutcome.REVIEW_REQUIRED,
                issue_codes=("gateway_empty_response",),
            ),
            calls,
        )
    return VerificationVerdict(outcome=VerificationOutcome.PASS, issue_codes=()), calls


def verify_mcq_answer(
    *,
    independent_solver_evidence: dict[str, Any] | None = None,
    **_kwargs: Any,
) -> VerificationVerdict:
    """Legacy signature — caller dict evidence is untrusted (AC-F01)."""

    if independent_solver_evidence is not None:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("caller_supplied_solver_evidence_rejected",),
        )
    return VerificationVerdict(
        outcome=VerificationOutcome.REVIEW_REQUIRED,
        issue_codes=("session_backed_verification_required",),
    )


def verify_multiselect_answer(
    *,
    independent_solver_evidence: dict[str, Any] | None = None,
    **_kwargs: Any,
) -> VerificationVerdict:
    return verify_mcq_answer(independent_solver_evidence=independent_solver_evidence)


def verify_numerical_answer(
    *,
    independent_solver_evidence: dict[str, Any] | None = None,
    tolerance: float | None = None,
    **_kwargs: Any,
) -> VerificationVerdict:
    import math

    if independent_solver_evidence is not None:
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("caller_supplied_solver_evidence_rejected",),
        )
    if tolerance is not None and (not math.isfinite(tolerance) or tolerance < 0):
        return VerificationVerdict(
            outcome=VerificationOutcome.REVIEW_REQUIRED,
            issue_codes=("numerical_tolerance_invalid",),
        )
    return VerificationVerdict(
        outcome=VerificationOutcome.REVIEW_REQUIRED,
        issue_codes=("session_backed_verification_required",),
    )


def verify_stem_assets(
    *,
    latex: str | None,
    has_image: bool,
    alt_text: str | None,
    image_provenance: str | None = None,
) -> VerificationVerdict:
    """D12-30: broken STEM assets require human review."""

    issues: list[str] = []
    if latex:
        if latex.count("$") % 2 != 0 or latex.count("$$") and latex.count("$$") % 2 != 0:
            issues.append("latex_unbalanced")
        if "\\frac{" in latex and "}" not in latex:
            issues.append("latex_malformed")
    if has_image and not (alt_text or "").strip():
        issues.append("image_alt_text_missing")
    if has_image and not (image_provenance or "").strip():
        issues.append("image_provenance_missing")
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


def verify_persisted_mcq_for_question(
    session: Session,
    *,
    question: Question,
    organization_id: str,
    institution_id: str | None,
    selected: str | None,
    correct: str | None,
) -> VerificationVerdict:
    return verify_persisted_mcq(
        session,
        question=question,
        organization_id=organization_id,
        institution_id=institution_id,
        selected=selected,
        correct=correct,
    )


__all__ = [
    "VerificationOutcome",
    "VerificationVerdict",
    "bounded_repair_allowed",
    "cognitive_competency_review",
    "run_scoped_generation_probe",
    "verify_mcq_answer",
    "verify_multiselect_answer",
    "verify_numerical_answer",
    "verify_persisted_mcq_for_question",
    "verify_stem_assets",
]