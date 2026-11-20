"""Synthetic two-paper issuance via injected Day8 gateway chain (PROD-47-03)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.jee_advanced.constants import PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.orchestration_chain import (
    ChainStage,
    OrchestrationChainResult,
    run_injected_author_solver_review_chain,
)
from app.jee_advanced.paper_pair_persistence import (
    PaperPairOutcome,
    PaperPairPersistRequest,
    PaperPairPersistResult,
    persist_two_paper_pair,
)
from app.jee_advanced.verification_orchestration import (
    VerificationOutcome,
    verify_stem_assets,
)
from app.orchestration.gateway.protocol import GenerationGateway


@dataclass(frozen=True, slots=True)
class IntegratedPairResult:
    chain: OrchestrationChainResult
    persist: PaperPairPersistResult
    gateway_calls_before_persist: int


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
    if not organization_id.strip():
        raise ValueError("organization_id required")
    chain = run_injected_author_solver_review_chain(
        gateway,
        item_id=question_ids[0],
        run_id=f"pair-gen-{idempotency_key}",
        organization_id=organization_id,
        scenario=scenario,
    )
    stem_gate = verify_stem_assets(latex=None, has_image=False, alt_text=None)
    if stem_gate.outcome != VerificationOutcome.PASS:
        return IntegratedPairResult(
            chain=chain,
            persist=PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=pair_correlation_id,
                test_definition_ids=(),
                checksum="",
                question_ids_by_paper={},
                issue_codes=stem_gate.issue_codes,
            ),
            gateway_calls_before_persist=len(gateway.call_history())
            if hasattr(gateway, "call_history")
            else chain.gateway_calls,
        )
    if chain.verdict.outcome != VerificationOutcome.PASS:
        return IntegratedPairResult(
            chain=chain,
            persist=PaperPairPersistResult(
                outcome=PaperPairOutcome.CONFLICT,
                pair_correlation_id=pair_correlation_id,
                test_definition_ids=(),
                checksum="",
                question_ids_by_paper={},
                issue_codes=chain.verdict.issue_codes,
            ),
            gateway_calls_before_persist=chain.gateway_calls,
        )

    calls_before = (
        len(gateway.call_history()) if hasattr(gateway, "call_history") else chain.gateway_calls
    )
    persist = persist_two_paper_pair(
        session,
        PaperPairPersistRequest(
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
        ),
    )
    return IntegratedPairResult(
        chain=chain,
        persist=persist,
        gateway_calls_before_persist=calls_before,
    )


REQUIRED_CHAIN_STAGES = (ChainStage.AUTHOR, ChainStage.SOLVER, ChainStage.REVIEW)