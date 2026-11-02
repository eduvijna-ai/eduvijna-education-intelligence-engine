from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from app.education_intelligence.context import ValidationContext
from app.education_intelligence.enums import ValidationStatus
from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.models.education_intelligence import ValidationAuditRun
from app.orchestration.canonical_mapping import draft_to_canonical
from app.orchestration.contracts import (
    DeterministicValidationSummary,
    DraftQuestionItem,
    ResolvedScope,
    ReviewVerdict,
    SolverResult,
)
from app.orchestration.control_session import _sqlite_memory_database
from app.orchestration.day6_reuse import (
    day6_run_versions_current,
    day6_summary_from_audit_run,
    find_accepted_day6_audit_run,
)
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.enums import OrchestrationRunStatus, ReviewVerdictStatus
from app.orchestration.math_tools import deterministic_math_check
from app.orchestration.nodes._helpers import (
    audit_node,
    get_request,
    next_attempt,
    pipeline_failure,
    timed_update,
)
from app.orchestration.state import OrchestrationGraphState
from app.root_cause_intelligence.day6_binding_verify import day6_binding_matches_persisted_run


def _may_persist_day6_validation(deps: OrchestrationDependencies) -> bool:
    """Persist Day6 audits on durable domain DB binds; skip in-memory harness savepoints."""
    if deps.control_session is None:
        return False
    bind = deps.session.get_bind()
    if bind is None:
        return False
    if _sqlite_memory_database(bind):
        return False
    return True


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
    evidence_snippet_by_revision = {
        item.source_revision_id: item.snippet for item in context.evidence
    }
    drafts = [DraftQuestionItem.model_validate(item) for item in state.get("draft_items") or []]
    solvers: dict[str, SolverResult] = {}
    for raw in state.get("solver_results") or []:
        solver = SolverResult.model_validate(raw)
        solvers[solver.item_id] = solver
    verdicts = [ReviewVerdict.model_validate(v) for v in state.get("review_verdicts") or []]
    prior_by_item = {
        str(entry.get("item_id")): entry
        for entry in (state.get("deterministic_validation") or [])
        if entry.get("item_id")
    }

    summaries: list[dict[str, Any]] = []
    validation_ctx = ValidationContext.create(
        deps.session,
        curriculum_version_id=scope.curriculum_version_id,
    )
    taxonomy_version = validation_ctx.taxonomy.version
    policy_version = validation_ctx.policy.version
    for draft in drafts:
        issue_codes: list[str] = []
        blocking = False
        repairable = False
        review_required = False

        for revision_id in draft.source_revision_ids:
            if revision_id not in allowed_revisions:
                issue_codes.append("provenance_unknown_revision")
                blocking = True

        injection_surfaces: list[str] = [draft.stem_text]
        for revision_id in draft.source_revision_ids:
            snippet = evidence_snippet_by_revision.get(revision_id)
            if snippet:
                injection_surfaces.append(snippet)
        if any("ignore previous instructions" in text.lower() for text in injection_surfaces):
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
        canonical_hash = canonical.canonical_hash()
        prior = prior_by_item.get(draft.item_id)
        day6_run_id: str | None = None
        input_hash: str | None = None
        learning_outcome_ids: list[str] = list(draft.learning_outcome_ids)
        competency_codes: list[str] = list(draft.competency_codes)
        reused_day6 = False
        if prior is not None and not blocking and prior.get("day6_validation_run_id"):
            prior_hash = str(prior.get("input_hash") or "")
            prior_los = list(prior.get("learning_outcome_ids") or learning_outcome_ids)
            prior_codes = list(prior.get("competency_codes") or competency_codes)
            if prior_hash == canonical_hash and day6_binding_matches_persisted_run(
                deps.session,
                item_id=draft.item_id,
                validation_run_id=str(prior.get("day6_validation_run_id")),
                input_hash=prior_hash,
                learning_outcome_ids=prior_los,
                competency_codes=prior_codes,
            ):
                prior_record = deps.session.get(
                    ValidationAuditRun, str(prior.get("day6_validation_run_id"))
                )
                if prior_record is None or not day6_run_versions_current(
                    prior_record,
                    taxonomy_version=taxonomy_version,
                    policy_version=policy_version,
                ):
                    prior_record = None
            else:
                prior_record = None
            if prior_record is not None:
                reused_day6 = True
                day6_run_id = str(prior.get("day6_validation_run_id"))
                input_hash = prior_hash
                learning_outcome_ids = prior_los
                competency_codes = prior_codes
        if not reused_day6:
            should_persist = (
                _may_persist_day6_validation(deps)
                and not blocking
                and not review_required
            )
            existing_run: ValidationAuditRun | None = None
            if should_persist:
                existing_run = find_accepted_day6_audit_run(
                    deps.session,
                    item_id=draft.item_id,
                    input_hash=canonical_hash,
                    scope=scope,
                    taxonomy_version=taxonomy_version,
                    policy_version=policy_version,
                )
            if existing_run is not None:
                day6_run_id, input_hash, learning_outcome_ids, competency_codes = (
                    day6_summary_from_audit_run(existing_run, item_id=draft.item_id)
                )
            else:
                try:
                    ei_summary = deps.education_service.validate_item(
                        canonical,
                        curriculum_version_id=scope.curriculum_version_id,
                        persist=should_persist,
                        actor_id=str(state.get("run_id") or "orchestration-day6"),
                        trusted_scope={
                            "organization_id": scope.organization_id,
                            "institution_id": scope.institution_id,
                            "curriculum_version_id": scope.curriculum_version_id,
                        },
                    )
                except Exception:
                    return pipeline_failure(
                        deps,
                        state,
                        "deterministic_validate",
                        started,
                        "day6_service_error",
                        attempt=attempt,
                    )
                day6_failed = (
                    ei_summary.blocking_failure
                    or ei_summary.aggregate_status == ValidationStatus.FAIL
                )
                if day6_failed:
                    issue_codes.append("day6_blocking_validation")
                    blocking = True
                elif ei_summary.aggregate_status == ValidationStatus.REVIEW_REQUIRED:
                    review_required = True
                if should_persist and not blocking:
                    record = deps.session.scalar(
                        select(ValidationAuditRun).where(
                            ValidationAuditRun.run_id == ei_summary.run_id
                        )
                    )
                    if record is not None:
                        day6_run_id = str(record.id)
                    input_hash = ei_summary.input_hash
                    validated = (ei_summary.metadata or {}).get("validated_items") or []
                    if validated and isinstance(validated[0], dict):
                        first = validated[0]
                        learning_outcome_ids = list(
                            first.get("learning_outcome_ids") or learning_outcome_ids
                        )
                        competency_codes = list(
                            first.get("competency_codes") or competency_codes
                        )

        summaries.append(
            DeterministicValidationSummary(
                item_id=draft.item_id,
                blocking=blocking,
                repairable=repairable and not blocking,
                review_required=review_required and not blocking and not repairable,
                issue_codes=issue_codes,
                day6_validation_run_id=day6_run_id,
                input_hash=input_hash,
                learning_outcome_ids=learning_outcome_ids,
                competency_codes=competency_codes,
                day6_content_fingerprint=canonical_hash,
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
    update: dict[str, Any] = {
        "deterministic_validation": summaries,
        "status": OrchestrationRunStatus.REVIEWING.value,
        "audit_refs": [audit_id],
    }
    if state.get("human_revalidate"):
        update["human_revalidate"] = False
    return timed_update(
        state,
        "deterministic_validate",
        started,
        update,
        attempt_map=attempt_map,
    )
