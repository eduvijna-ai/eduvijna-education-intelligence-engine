from __future__ import annotations

import time
from typing import Any

from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.orchestration.contracts import ResolvedScope
from app.orchestration.dependencies import OrchestrationDependencies
from app.orchestration.nodes._helpers import audit_node, get_request, next_attempt, timed_update
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
    allowed_sources = list(
        dict.fromkeys(
            (state.get("source_revision_ids") or [])
            + (request.metadata_json.get("allowed_source_revision_ids") or [])
        )
    )

    diagnostic_results = state.get("diagnostic_results") or []
    for entry in diagnostic_results:
        item_id = str(entry.get("item_id"))
        for tag_data in entry.get("option_tags") or []:
            if tag_data.get("is_correct"):
                continue
            misconception = tag_data.get("misconception_code")
            if not misconception:
                continue
            tag = OptionDiagnosticTag.model_validate(
                {
                    **tag_data,
                    "item_id": item_id,
                    "validation_status": tag_data.get("validation_status")
                    or DiagnosticValidationStatus.PASS.value,
                }
            )
            target_concept = (
                request.metadata_json.get("root_cause_target_concept_code") or "multi-step-addition"
            )
            analysis = service.analyze(
                RootCauseDiagnosticRequest(
                    item_id=item_id,
                    option_key=str(tag_data.get("option_key")),
                    misconception_code=str(misconception),
                    taxonomy_version=str(
                        tag_data.get("taxonomy_version") or "misconception-taxonomy@v1"
                    ),
                    tag=tag,
                    curriculum_version_id=curriculum_version_id,
                    graph_snapshot=snapshot,
                    target_concept_code=str(target_concept),
                    organization_id=graph_scope.organization_id,
                    institution_id=graph_scope.institution_id,
                    allowed_source_revision_ids=allowed_sources,
                )
            )
            results.append(analysis.model_dump(mode="json"))

    audit_id = audit_node(
        deps,
        state,
        "root_cause_enrich",
        "completed",
        attempt=attempt,
        payload={"result_count": len(results)},
    )
    return timed_update(
        state,
        "root_cause_enrich",
        started,
        {
            "root_cause_results": results,
            "audit_refs": [audit_id],
        },
        attempt_map=attempt_map,
    )
