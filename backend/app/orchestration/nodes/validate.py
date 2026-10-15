from __future__ import annotations

import time
from typing import Any

from app.education_intelligence.enums import ValidationStatus
from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.orchestration.canonical_mapping import draft_to_canonical
from app.orchestration.contracts import (
    DeterministicValidationSummary,
    DraftQuestionItem,
    ResolvedScope,
    ReviewVerdict,
    SolverResult,
)
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus, ReviewVerdictStatus
from app.orchestration.math_tools import deterministic_math_check
from app.orchestration.nodes._helpers import audit_node, get_request, next_attempt, timed_update
from app.orchestration.state import OrchestrationGraphState


def deterministic_validate_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "deterministic_validate")
    request = get_request(state)
    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    context = KnowledgeContextPack.model_validate(state.get("knowledge_context") or {})
    allowed_revisions = {item.source_revision_id for item in context.evidence}
    allowed_evidence_refs = {item.citation_label for item in context.evidence}
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    solvers: dict[str, SolverResult] = {}
    for raw in state.get("solver_results") or []:
        solver = SolverResult.model_validate(raw)
        solvers[solver.item_id] = solver
    verdicts = [ReviewVerdict.model_validate(v) for v in state.get("review_verdicts") or []]

    summaries: list[dict[str, Any]] = []
    for draft in drafts:
        issue_codes: list[str] = []
        blocking = False
        repairable = False
        review_required = False

        for revision_id in draft.source_revision_ids:
            if revision_id not in allowed_revisions:
                issue_codes.append("provenance_unknown_revision")
                blocking = True

        if "ignore previous instructions" in draft.stem_text.lower():
            issue_codes.append("injection_evidence_control")
            repairable = True
            marks_mismatch = (
                draft.marks is not None
                and request.marks is not None
                and draft.marks != request.marks
            )
            if marks_mismatch:
                issue_codes.append("injection_control_metadata")
                blocking = True

        solver_result = solvers.get(draft.item_id)
        if solver_result is not None and not solver_result.agrees_with_author:
            issue_codes.append("solver_author_disagreement")
            repairable = True
        if solver_result is not None:
            check_status, mismatch = deterministic_math_check(draft, solver_result)
            if mismatch:
                issue_codes.append("deterministic_math_mismatch")
                repairable = True
            elif check_status == "unknown":
                review_required = True

        for verdict in verdicts:
            if verdict.item_id != draft.item_id:
                continue
            for ref in verdict.evidence_refs:
                if ref and ref not in allowed_evidence_refs:
                    issue_codes.append("reviewer_unknown_evidence_ref")
                    blocking = True
            if verdict.status == ReviewVerdictStatus.REJECT:
                issue_codes.extend(verdict.issue_codes)
                blocking = True
            elif verdict.status == ReviewVerdictStatus.REPAIR:
                issue_codes.extend(verdict.issue_codes)
                repairable = True
            elif verdict.status == ReviewVerdictStatus.REVIEW_REQUIRED:
                review_required = True

        canonical = draft_to_canonical(draft, scope, request_marks=request.marks)
        ei_summary = deps.education_service.validate_item(
            canonical,
            curriculum_version_id=scope.curriculum_version_id,
            persist=False,
        )
        if ei_summary.blocking_failure or ei_summary.aggregate_status == ValidationStatus.FAIL:
            issue_codes.append("day6_blocking_validation")
            blocking = True
        elif ei_summary.aggregate_status == ValidationStatus.REVIEW_REQUIRED:
            review_required = True

        summaries.append(
            DeterministicValidationSummary(
                item_id=draft.item_id,
                blocking=blocking,
                repairable=repairable and not blocking,
                review_required=review_required and not blocking and not repairable,
                issue_codes=issue_codes,
            ).model_dump(mode="json")
        )

    audit_id = audit_node(
        deps,
        state,
        "deterministic_validate",
        "ok",
        attempt=attempt,
        payload={"items": len(summaries)},
    )
    return timed_update(
        state,
        "deterministic_validate",
        started,
        {
            "deterministic_validation": summaries,
            "status": OrchestrationRunStatus.REVIEWING.value,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
