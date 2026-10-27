from __future__ import annotations

import time
from typing import Any

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.knowledge_intelligence.contracts import KnowledgeContextPack
from app.orchestration.contracts import ResolvedScope
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.nodes._helpers import audit_node, get_request, next_attempt, timed_update
from app.orchestration.root_cause_trust import (
    build_trusted_validation_from_state,
    item_allowed_source_revision_ids,
)
from app.orchestration.state import OrchestrationGraphState
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.prerequisite_intelligence.loader import load_prerequisite_graph_snapshot
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.service import RootCauseIntelligenceService


def root_cause_enrich_node(
    state: OrchestrationGraphState, deps: OrchestrationDependencies
) -> dict[str, Any]:
    started = time.perf_counter()
    attempt, attempt_map = next_attempt(state, "root_cause_enrich")
    request = get_request(state)
    results: list[dict[str, Any]] = list(state.get("root_cause_results") or [])

    if not request.root_cause_enrichment_enabled():
        return timed_update(
            state,
            "root_cause_enrich",
            started,
            {"root_cause_results": results},
            attempt_map=attempt_map,
        )

    scope = ResolvedScope.model_validate(state.get("resolved_scope") or {})
    service = RootCauseIntelligenceService()
    curriculum_version_id = scope.curriculum_version_id or request.curriculum_version_id
    if not curriculum_version_id:
        return timed_update(
            state,
            "root_cause_enrich",
            started,
            {
                "errors": ["root_cause_missing_curriculum_version"],
                "pipeline_halt": True,
            },
            attempt_map=attempt_map,
        )

    graph_scope = PrerequisiteGraphScope(
        curriculum_version_id=curriculum_version_id,
        grade_year_code=scope.grade_year_code or request.grade_year_code,
        medium_code=scope.medium_code or request.medium_code,
        subject_code=scope.subject_code or request.subject_code,
        organization_id=scope.organization_id or request.organization_id,
        institution_id=scope.institution_id or request.institution_id,
        teacher_id=scope.teacher_id or request.teacher_id,
    )
    snapshot = load_prerequisite_graph_snapshot(deps.session, graph_scope)
    context = KnowledgeContextPack.model_validate(state.get("knowledge_context") or {})
    diagnostic_validation = list(state.get("diagnostic_validation") or [])
    diagnostic_audit_refs = list(state.get("audit_refs") or [])
    deterministic_by_item = {
        str(entry.get("item_id")): entry
        for entry in (state.get("deterministic_validation") or [])
    }

    draft_by_item = {
        str(item.get("item_id")): item for item in (state.get("draft_items") or [])
    }
    diagnostic_results = state.get("diagnostic_results") or []
    eligible_tags = 0
    for entry in diagnostic_results:
        item_id = str(entry.get("item_id"))
        for tag_data in entry.get("option_tags") or []:
            if tag_data.get("is_correct"):
                continue
            misconception = tag_data.get("misconception_code")
            if not misconception:
                continue
            validation_status = tag_data.get("validation_status")
            if validation_status is None:
                continue
            if str(validation_status) != "pass":
                continue
            eligible_tags += 1
            tag = OptionDiagnosticTag.model_validate(
                {
                    **tag_data,
                    "item_id": item_id,
                    "validation_status": validation_status,
                }
            )
            det = deterministic_by_item.get(item_id) or {}
            draft = draft_by_item.get(item_id) or {}
            draft_meta = draft.get("metadata_json") or {}
            concept_codes = list(
                draft.get("concept_codes")
                or draft_meta.get("concept_codes")
                or scope.concept_codes
                or []
            )
            target_concept = concept_codes[0] if concept_codes else ""
            if not target_concept:
                continue
            taxonomy_version = str(
                tag_data.get("taxonomy_version") or "misconception-taxonomy@v1"
            )
            trusted = build_trusted_validation_from_state(
                item_id=item_id,
                option_key=str(tag_data.get("option_key")),
                misconception_code=str(misconception),
                taxonomy_version=taxonomy_version,
                diagnostic_validation=diagnostic_validation,
                diagnostic_results=diagnostic_results,
                diagnostic_audit_refs=diagnostic_audit_refs,
            )
            allowed_sources = item_allowed_source_revision_ids(draft, context)
            analysis = service.analyze(
                RootCauseDiagnosticRequest(
                    item_id=item_id,
                    option_key=str(tag_data.get("option_key")),
                    misconception_code=str(misconception),
                    taxonomy_version=taxonomy_version,
                    tag=tag,
                    curriculum_version_id=curriculum_version_id,
                    graph_snapshot=snapshot,
                    target_concept_code=target_concept,
                    organization_id=graph_scope.organization_id,
                    institution_id=graph_scope.institution_id,
                    teacher_id=graph_scope.teacher_id,
                    allowed_source_revision_ids=allowed_sources,
                    day6_blocking=bool(det.get("blocking")),
                ),
                trusted=trusted,
            )
            item_audit = audit_node(
                deps,
                state,
                "root_cause_item",
                analysis.verdict_status.value,
                attempt=attempt,
                issue_codes=[code.value for code in analysis.issue_codes],
                source_revision_ids=allowed_sources,
                payload={
                    "item_id": item_id,
                    "option_key": str(tag_data.get("option_key")),
                    "misconception_code": str(misconception),
                    "verdict_status": analysis.verdict_status.value,
                    "audit_ref": analysis.audit_ref,
                    "allowed_source_revision_ids": allowed_sources,
                    "trusted": trusted is not None,
                },
            )
            dumped = analysis.model_dump(mode="json")
            dumped["orchestration_audit_ref"] = item_audit
            results.append(dumped)

    audit_id = audit_node(
        deps,
        state,
        "root_cause_enrich",
        "completed",
        attempt=attempt,
        payload={
            "result_count": len(results),
            "eligible_tag_count": eligible_tags,
            "item_audit_refs": [
                entry.get("orchestration_audit_ref")
                for entry in results
                if entry.get("orchestration_audit_ref")
            ],
        },
    )
    return timed_update(
        state,
        "root_cause_enrich",
        started,
        {
            "root_cause_results": results,
            "root_cause_eligible_tag_count": eligible_tags,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
