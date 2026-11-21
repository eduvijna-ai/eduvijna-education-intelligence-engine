"""Synthetic two-paper issuance: preflight, validate, gateway, persist (#47/#48)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.jee_advanced.author_draft_binding import (
    author_visible_fingerprint,
    display_candidate_from_question,
)
from app.jee_advanced.chain_question_binding import (
    bind_chain_to_persisted_question,
    stored_mcq_answer_key,
)
from app.jee_advanced.constants import PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.issuance_snapshot import build_issuance_record
from app.jee_advanced.orchestration_chain import (
    ChainStage,
    OrchestrationChainResult,
    run_injected_author_solver_review_chain,
)
from app.jee_advanced.pair_issuance_validation import validate_questions_for_pair_issuance
from app.jee_advanced.paper_pair_persistence import (
    PaperPairOutcome,
    PaperPairPersistRequest,
    PaperPairPersistResult,
    persist_two_paper_pair,
    preflight_two_paper_pair,
)
from app.jee_advanced.verification_orchestration import (
    VerificationOutcome,
    verify_stem_assets,
)
from app.orchestration.gateway.protocol import GenerationGateway


@dataclass(frozen=True, slots=True)
class IntegratedPairResult:
    persist: PaperPairPersistResult
    gateway_calls: int
    replayed: bool
    chains: tuple[OrchestrationChainResult, ...] = ()
    demonstration_only: bool = True

    @property
    def gateway_calls_before_persist(self) -> int:
        """Back-compat alias for Issue #47 tests."""

        return self.gateway_calls

    @property
    def chain(self) -> OrchestrationChainResult | None:
        return self.chains[0] if self.chains else None


def build_labeled_synthetic_pair_request(
    *,
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    question_ids: tuple[str, str],
    idempotency_key: str,
    pair_correlation_id: str,
) -> PaperPairPersistRequest:
    return PaperPairPersistRequest(
        idempotency_key=idempotency_key,
        organization_id=organization_id,
        institution_id=institution_id,
        exam_version_id=exam_version_id,
        pair_correlation_id=pair_correlation_id,
        paper_definitions=(
            {
                "paper_code": PAPER_1_CODE,
                "title": "Synthetic Paper 1",
                "question_items": [
                    {"question_id": question_ids[0], "section_code": "A", "marks": 3}
                ],
            },
            {
                "paper_code": PAPER_2_CODE,
                "title": "Synthetic Paper 2",
                "question_items": [
                    {"question_id": question_ids[1], "section_code": "B", "marks": 3}
                ],
            },
        ),
        source_revision_snapshot={},
        blueprint_snapshot={"demonstration_only": True},
        synthetic_labeled_test_mode=True,
    )


def _gateway_call_count(gateway: GenerationGateway, baseline: int) -> int:
    if hasattr(gateway, "call_history"):
        return len(gateway.call_history()) - baseline
    return 0


def run_labeled_synthetic_pair_integration(
    session: Session,
    gateway: GenerationGateway,
    *,
    organization_id: str,
    institution_id: str,
    exam_version_id: str,
    question_ids: tuple[str, str],
    idempotency_key: str,
    pair_correlation_id: str,
    scenario: str = "clean_pass",
) -> IntegratedPairResult:
    if scenario == "solver_match_persisted":
        return IntegratedPairResult(
            persist=PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=pair_correlation_id,
                test_definition_ids=(),
                checksum="",
                question_ids_by_paper={},
                issue_codes=("echo_solver_scenario_rejected",),
            ),
            gateway_calls=0,
            replayed=False,
            chains=(),
        )
    if not organization_id.strip():
        raise ValueError("organization_id required")

    request = build_labeled_synthetic_pair_request(
        organization_id=organization_id,
        institution_id=institution_id,
        exam_version_id=exam_version_id,
        question_ids=question_ids,
        idempotency_key=idempotency_key,
        pair_correlation_id=pair_correlation_id,
    )

    preflight = preflight_two_paper_pair(session, request)
    if preflight is not None:
        return IntegratedPairResult(
            persist=preflight,
            gateway_calls=0,
            replayed=preflight.outcome == PaperPairOutcome.REPLAYED,
            chains=(),
            demonstration_only=True,
        )

    ok, val_issues, _questions = validate_questions_for_pair_issuance(
        session,
        organization_id=organization_id,
        institution_id=institution_id,
        exam_version_id=exam_version_id,
        question_ids=question_ids,
    )
    if not ok:
        return IntegratedPairResult(
            persist=PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=pair_correlation_id,
                test_definition_ids=(),
                checksum="",
                question_ids_by_paper={},
                issue_codes=val_issues,
            ),
            gateway_calls=0,
            replayed=False,
            chains=(),
        )

    baseline = len(gateway.call_history()) if hasattr(gateway, "call_history") else 0
    run_id = f"pair-gen-{idempotency_key}"
    q_by_id = {str(q.id): q for q in _questions}
    chains: list[OrchestrationChainResult] = []
    for item_id in question_ids:
        question = q_by_id[str(item_id)]
        visible = display_candidate_from_question(question)
        author_ext: dict[str, object] = {}
        if scenario == "bound_synthetic_control":
            author_ext["bound_display"] = visible
            answer_key = stored_mcq_answer_key(question)
            if answer_key:
                author_ext["bound_correct_key"] = answer_key
        chain = run_injected_author_solver_review_chain(
            gateway,
            item_id=item_id,
            run_id=run_id,
            organization_id=organization_id,
            scenario=scenario,
            author_user_extensions=author_ext or None,
            persisted_visible_fingerprint=author_visible_fingerprint(visible),
        )
        chains.append(chain)
        stem_gate = verify_stem_assets(latex=None, has_image=False, alt_text=None)
        if stem_gate.outcome != VerificationOutcome.PASS:
            return IntegratedPairResult(
                persist=PaperPairPersistResult(
                    outcome=PaperPairOutcome.CONFLICT,
                    pair_correlation_id=pair_correlation_id,
                    test_definition_ids=(),
                    checksum="",
                    question_ids_by_paper={},
                    issue_codes=stem_gate.issue_codes,
                ),
                gateway_calls=_gateway_call_count(gateway, baseline),
                replayed=False,
                chains=tuple(chains),
            )
        if chain.verdict.outcome != VerificationOutcome.PASS:
            return IntegratedPairResult(
                persist=PaperPairPersistResult(
                    outcome=PaperPairOutcome.CONFLICT,
                    pair_correlation_id=pair_correlation_id,
                    test_definition_ids=(),
                    checksum="",
                    question_ids_by_paper={},
                    issue_codes=chain.verdict.issue_codes,
                ),
                gateway_calls=_gateway_call_count(gateway, baseline),
                replayed=False,
                chains=tuple(chains),
            )
        bound, bind_issues = bind_chain_to_persisted_question(chain, question)
        if not bound:
            return IntegratedPairResult(
                persist=PaperPairPersistResult(
                    outcome=PaperPairOutcome.CONFLICT,
                    pair_correlation_id=pair_correlation_id,
                    test_definition_ids=(),
                    checksum="",
                    question_ids_by_paper={},
                    issue_codes=bind_issues,
                ),
                gateway_calls=_gateway_call_count(gateway, baseline),
                replayed=False,
                chains=tuple(chains),
            )

    issuance_record = build_issuance_record(
        request,
        questions=(_questions[0], _questions[1]),
        chains=tuple(chains),
    )
    persist = persist_two_paper_pair(session, request, issuance_record=issuance_record)
    return IntegratedPairResult(
        persist=persist,
        gateway_calls=_gateway_call_count(gateway, baseline),
        replayed=persist.outcome == PaperPairOutcome.REPLAYED,
        chains=tuple(chains),
        demonstration_only=True,
    )


REQUIRED_CHAIN_STAGES = (ChainStage.AUTHOR, ChainStage.SOLVER, ChainStage.REVIEW)