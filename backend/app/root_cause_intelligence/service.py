from __future__ import annotations

from uuid import uuid4

from app.prerequisite_intelligence.contracts import GraphTraversalLimits
from app.prerequisite_intelligence.enums import EdgeProvenanceClass
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest, RootCauseResult
from app.root_cause_intelligence.enums import (
    DEFAULT_ROOT_CAUSE_MAPPING_VERSION,
    RootCauseIssueCode,
    RootCauseVerdictStatus,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping
from app.root_cause_intelligence.preflight import run_root_cause_preflight
from app.root_cause_intelligence.ranking import rank_root_cause_hypotheses


class RootCauseIntelligenceService:
    def analyze(self, request: RootCauseDiagnosticRequest) -> RootCauseResult:
        preflight = run_root_cause_preflight(request)
        mapping = load_root_cause_mapping(DEFAULT_ROOT_CAUSE_MAPPING_VERSION)
        mapping_entry = mapping.resolve(request.misconception_code)
        issue_codes = list(preflight.issue_codes)
        field_paths = list(preflight.field_paths)

        if mapping_entry is None:
            issue_codes.append(RootCauseIssueCode.UNKNOWN_MISCONCEPTION)
            field_paths.append("misconception_code")
            return RootCauseResult(
                item_id=request.item_id,
                option_key=request.option_key,
                misconception_code=request.misconception_code,
                verdict_status=RootCauseVerdictStatus.FAIL,
                issue_codes=issue_codes,
                field_paths=field_paths,
                mapping_version=mapping.version,
                graph_snapshot_id=request.graph_snapshot.snapshot_id,
                graph_checksum=request.graph_snapshot.checksum,
                audit_ref=str(uuid4()),
            )

        if preflight.blocking:
            status = RootCauseVerdictStatus.FAIL
            if RootCauseIssueCode.CORRECT_OPTION_TAGGED in issue_codes:
                status = RootCauseVerdictStatus.REVIEW_REQUIRED
            return RootCauseResult(
                item_id=request.item_id,
                option_key=request.option_key,
                misconception_code=request.misconception_code,
                verdict_status=status,
                issue_codes=issue_codes,
                field_paths=field_paths,
                mapping_version=mapping.version,
                graph_snapshot_id=request.graph_snapshot.snapshot_id,
                graph_checksum=request.graph_snapshot.checksum,
                audit_ref=str(uuid4()),
            )

        unauthorized = [
            edge.edge_id
            for edge in request.graph_snapshot.edges
            if edge.provenance_class == EdgeProvenanceClass.OFFICIAL
            and edge.source_revision_id
            and request.allowed_source_revision_ids
            and edge.source_revision_id not in set(request.allowed_source_revision_ids)
        ]
        if unauthorized:
            issue_codes.append(RootCauseIssueCode.UNAUTHORIZED_SOURCE)
            field_paths.append("graph_snapshot.edges")

        hypotheses = rank_root_cause_hypotheses(
            request.graph_snapshot,
            mapping_entry,
            target_concept_code=request.target_concept_code,
            limits=GraphTraversalLimits(max_depth=8, max_paths=8, max_nodes=48),
        )
        if not hypotheses:
            issue_codes.append(RootCauseIssueCode.NO_PREREQUISITE_PATH)
            field_paths.append("hypotheses")
            verdict = RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE
        elif len(hypotheses) >= 2 and hypotheses[0].support_score == hypotheses[1].support_score:
            issue_codes.append(RootCauseIssueCode.AMBIGUOUS_PATH)
            verdict = RootCauseVerdictStatus.REVIEW_REQUIRED
        elif issue_codes:
            verdict = RootCauseVerdictStatus.REVIEW_REQUIRED
        else:
            verdict = RootCauseVerdictStatus.PASS

        return RootCauseResult(
            item_id=request.item_id,
            option_key=request.option_key,
            misconception_code=request.misconception_code,
            verdict_status=verdict,
            issue_codes=issue_codes,
            field_paths=field_paths,
            hypotheses=hypotheses,
            mapping_version=mapping.version,
            graph_snapshot_id=request.graph_snapshot.snapshot_id,
            graph_checksum=request.graph_snapshot.checksum,
            audit_ref=str(uuid4()),
            metadata_json={
                "disclaimer": (
                    "Hypotheses describe possible prerequisite mechanisms; "
                    "not demonstrated learner mastery."
                ),
            },
        )
