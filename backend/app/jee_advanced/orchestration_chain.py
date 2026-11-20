"""Injected Day8 gateway author→solver→review chain for JEE Advanced (READY-03)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.jee_advanced.independent_verification import VerificationOutcome, VerificationVerdict
from app.orchestration.enums import GenerationNodeRole
from app.orchestration.gateway.fake import FakeGenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest


class ChainStage(StrEnum):
    AUTHOR = "author"
    SOLVER = "solver"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class OrchestrationChainResult:
    verdict: VerificationVerdict
    stages_completed: tuple[ChainStage, ...]
    gateway_calls: int
    audit_ids: tuple[str, ...]


def run_injected_author_solver_review_chain(
    gateway: FakeGenerationGateway,
    *,
    item_id: str,
    run_id: str,
    organization_id: str,
    scenario: str = "clean_pass",
    max_repairs: int = 2,
    repairs_used: int = 0,
) -> OrchestrationChainResult:
    """Execute AUTHOR→SOLVER→PATTERN_REVIEW; fail on veto/repair budget/reject scenario."""

    stages: list[ChainStage] = []
    audit_ids: list[str] = []

    if repairs_used > max_repairs:
        return OrchestrationChainResult(
            verdict=VerificationVerdict(
                outcome=VerificationOutcome.FAIL,
                issue_codes=("repair_budget_exceeded",),
            ),
            stages_completed=tuple(stages),
            gateway_calls=len(gateway.call_history()),
            audit_ids=tuple(audit_ids),
        )

    if not organization_id.strip():
        return OrchestrationChainResult(
            verdict=VerificationVerdict(
                outcome=VerificationOutcome.REVIEW_REQUIRED,
                issue_codes=("organization_scope_missing",),
            ),
            stages_completed=tuple(stages),
            gateway_calls=0,
            audit_ids=(),
        )

    try:
        author_resp = gateway.generate(
            GenerationRequest(
                role=GenerationNodeRole.AUTHOR,
                prompt_version="jee-adv-chain@v1",
                system_prompt="author",
                user_payload={
                    "item_id": item_id,
                    "run_id": run_id,
                    "organization_id": organization_id,
                },
                output_schema_name="author_item_v1",
                scenario=scenario,
            )
        )
        stages.append(ChainStage.AUTHOR)
        audit_ids.append(author_resp.gateway_request_id or "author-unknown")

        solver_resp = gateway.generate(
            GenerationRequest(
                role=GenerationNodeRole.SOLVER,
                prompt_version="jee-adv-chain@v1",
                system_prompt="solver",
                user_payload={
                    "item_id": item_id,
                    "run_id": run_id,
                    "stem": author_resp.parsed,
                },
                output_schema_name="solver_item_v1",
                scenario=scenario,
            )
        )
        stages.append(ChainStage.SOLVER)
        audit_ids.append(solver_resp.gateway_request_id or "solver-unknown")

        parsed_solver = solver_resp.parsed if isinstance(solver_resp.parsed, dict) else {}
        if scenario in {"author_reject", "solver_reject"}:
            return OrchestrationChainResult(
                verdict=VerificationVerdict(
                    outcome=VerificationOutcome.FAIL,
                    issue_codes=("orchestration_rejected",),
                ),
                stages_completed=tuple(stages),
                gateway_calls=len(gateway.call_history()),
                audit_ids=tuple(audit_ids),
            )

        review_resp = gateway.generate(
            GenerationRequest(
                role=GenerationNodeRole.PATTERN_REVIEW,
                prompt_version="jee-adv-chain@v1",
                system_prompt="review",
                user_payload={
                    "item_id": item_id,
                    "run_id": run_id,
                    "solver": parsed_solver,
                },
                output_schema_name="review_item_v1",
                scenario=scenario,
            )
        )
        stages.append(ChainStage.REVIEW)
        audit_ids.append(review_resp.gateway_request_id or "review-unknown")

        review_parsed = review_resp.parsed if isinstance(review_resp.parsed, dict) else {}
        verdict_raw = str(review_parsed.get("status") or review_parsed.get("verdict") or "")
        if verdict_raw.lower() in {"reject", "review_required", "repair"}:
            return OrchestrationChainResult(
                verdict=VerificationVerdict(
                    outcome=VerificationOutcome.REVIEW_REQUIRED,
                    issue_codes=("reviewer_veto",),
                ),
                stages_completed=tuple(stages),
                gateway_calls=len(gateway.call_history()),
                audit_ids=tuple(audit_ids),
            )
        if str(parsed_solver.get("check_status") or "") != "ok":
            return OrchestrationChainResult(
                verdict=VerificationVerdict(
                    outcome=VerificationOutcome.REVIEW_REQUIRED,
                    issue_codes=("solver_check_failed",),
                ),
                stages_completed=tuple(stages),
                gateway_calls=len(gateway.call_history()),
                audit_ids=tuple(audit_ids),
            )
        if not parsed_solver.get("proposed_answer_key"):
            return OrchestrationChainResult(
                verdict=VerificationVerdict(
                    outcome=VerificationOutcome.REVIEW_REQUIRED,
                    issue_codes=("solver_evidence_incomplete",),
                ),
                stages_completed=tuple(stages),
                gateway_calls=len(gateway.call_history()),
                audit_ids=tuple(audit_ids),
            )

        return OrchestrationChainResult(
            verdict=VerificationVerdict(
                outcome=VerificationOutcome.PASS,
                issue_codes=(),
                demonstration_only=True,
            ),
            stages_completed=tuple(stages),
            gateway_calls=len(gateway.call_history()),
            audit_ids=tuple(audit_ids),
        )
    except GenerationGatewayError as exc:
        return OrchestrationChainResult(
            verdict=VerificationVerdict(
                outcome=VerificationOutcome.FAIL,
                issue_codes=(str(exc.code),),
            ),
            stages_completed=tuple(stages),
            gateway_calls=len(gateway.call_history()),
            audit_ids=tuple(audit_ids),
        )