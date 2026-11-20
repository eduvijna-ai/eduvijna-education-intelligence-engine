"""Injected gateway author→solver→review chain for JEE Advanced (PROD-47-03)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.jee_advanced.independent_verification import VerificationOutcome, VerificationVerdict
from app.orchestration.enums import GenerationNodeRole, ReviewVerdictStatus
from app.orchestration.gateway.protocol import GenerationGateway
from app.orchestration.gateway.types import GenerationGatewayError, GenerationRequest


class ChainStage(StrEnum):
    AUTHOR = "author"
    SOLVER = "solver"
    REVIEW = "review"
    REPAIR = "repair"


_AFFIRMATIVE_REVIEW = frozenset(
    {ReviewVerdictStatus.PASS.value, "approved", "pass"}
)
_NEGATIVE_REVIEW = frozenset(
    {
        ReviewVerdictStatus.REJECT.value,
        ReviewVerdictStatus.REVIEW_REQUIRED.value,
        "reject",
        "review_required",
        "repair",
        ReviewVerdictStatus.REPAIR.value,
    }
)


@dataclass(frozen=True, slots=True)
class OrchestrationChainResult:
    verdict: VerificationVerdict
    stages_completed: tuple[ChainStage, ...]
    gateway_calls: int
    audit_ids: tuple[str, ...]
    hitl_pending: bool = False


def _review_status_ok(review_parsed: dict[str, object]) -> bool:
    raw = str(review_parsed.get("status") or review_parsed.get("verdict") or "").strip().lower()
    if not raw:
        return False
    if raw in _NEGATIVE_REVIEW:
        return False
    return raw in _AFFIRMATIVE_REVIEW


def run_injected_author_solver_review_chain(
    gateway: GenerationGateway,
    *,
    item_id: str,
    run_id: str,
    organization_id: str,
    scenario: str = "clean_pass",
    max_repairs: int = 2,
    repairs_used: int = 0,
) -> OrchestrationChainResult:
    """AUTHOR→SOLVER→REVIEW (+ optional REPAIR); require affirmative reviewer PASS."""

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
                    "draft": author_resp.parsed,
                },
                output_schema_name="review_item_v1",
                scenario=scenario,
            )
        )
        stages.append(ChainStage.REVIEW)
        audit_ids.append(review_resp.gateway_request_id or "review-unknown")

        review_parsed = review_resp.parsed if isinstance(review_resp.parsed, dict) else {}
        verdict_raw = str(review_parsed.get("status") or review_parsed.get("verdict") or "").lower()

        if scenario == "human_review" or verdict_raw == ReviewVerdictStatus.REVIEW_REQUIRED.value:
            return OrchestrationChainResult(
                verdict=VerificationVerdict(
                    outcome=VerificationOutcome.REVIEW_REQUIRED,
                    issue_codes=("hitl_pending",),
                ),
                stages_completed=tuple(stages),
                gateway_calls=len(gateway.call_history()),
                audit_ids=tuple(audit_ids),
                hitl_pending=True,
            )

        if verdict_raw == ReviewVerdictStatus.REPAIR.value or verdict_raw == "repair":
            if repairs_used >= max_repairs:
                return OrchestrationChainResult(
                    verdict=VerificationVerdict(
                        outcome=VerificationOutcome.FAIL,
                        issue_codes=("repair_budget_exceeded",),
                    ),
                    stages_completed=tuple(stages),
                    gateway_calls=len(gateway.call_history()),
                    audit_ids=tuple(audit_ids),
                )
            repair_resp = gateway.generate(
                GenerationRequest(
                    role=GenerationNodeRole.REPAIR,
                    prompt_version="jee-adv-chain@v1",
                    system_prompt="repair",
                    user_payload={
                        "item_id": item_id,
                        "run_id": run_id,
                        "repair_instructions": review_parsed.get("repair_instructions") or [],
                        "draft": author_resp.parsed,
                    },
                    output_schema_name="repair_item_v1",
                    scenario=scenario,
                )
            )
            stages.append(ChainStage.REPAIR)
            audit_ids.append(repair_resp.gateway_request_id or "repair-unknown")
            review_resp = gateway.generate(
                GenerationRequest(
                    role=GenerationNodeRole.PATTERN_REVIEW,
                    prompt_version="jee-adv-chain@v1",
                    system_prompt="review",
                    user_payload={
                        "item_id": item_id,
                        "run_id": run_id,
                        "solver": parsed_solver,
                        "draft": author_resp.parsed,
                        "repaired": True,
                    },
                    output_schema_name="review_item_v1",
                    scenario="repair_then_pass",
                )
            )
            stages.append(ChainStage.REVIEW)
            audit_ids.append(review_resp.gateway_request_id or "review-post-repair")
            review_parsed = review_resp.parsed if isinstance(review_resp.parsed, dict) else {}

        if not _review_status_ok(review_parsed):
            issue = "reviewer_verdict_missing" if not verdict_raw else "reviewer_veto"
            return OrchestrationChainResult(
                verdict=VerificationVerdict(
                    outcome=VerificationOutcome.REVIEW_REQUIRED,
                    issue_codes=(issue,),
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
            gateway_calls=len(gateway.call_history()) if hasattr(gateway, "call_history") else 0,
            audit_ids=tuple(audit_ids),
        )