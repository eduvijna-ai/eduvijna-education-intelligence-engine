from __future__ import annotations

from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import GraphTraversalLimits
from app.prerequisite_intelligence.enums import (
    EdgeProvenanceClass,
    GraphAuditStatus,
    GraphIssueCode,
)
from app.prerequisite_intelligence.stable_ids import stable_audit_ref
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
        audit_ref = stable_audit_ref(
            "root_cause",
            request.item_id,
            request.option_key,
            request.misconception_code,
            request.graph_snapshot.checksum,
        )

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
                audit_ref=audit_ref,
            )

        if preflight.blocking:
            status = RootCauseVerdictStatus.FAIL
            if RootCauseIssueCode.CORRECT_OPTION_TAGGED in issue_codes:
                status = RootCauseVerdictStatus.REVIEW_REQUIRED
            elif RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in issue_codes:
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
                audit_ref=audit_ref,
            )

        allowed = set(request.allowed_source_revision_ids or [])
        snapshot_allow = set(
            request.graph_snapshot.metadata_json.get("authorized_revision_ids") or []
        )
        if not allowed and snapshot_allow:
            issue_codes.append(RootCauseIssueCode.SNAPSHOT_ALLOWLIST_SPOOF)
            field_paths.append("graph_snapshot.metadata_json.authorized_revision_ids")

        has_official = any(
            edge.provenance_class == EdgeProvenanceClass.OFFICIAL
            for edge in request.graph_snapshot.edges
        )
        if has_official and not allowed:
            issue_codes.append(RootCauseIssueCode.UNAUTHORIZED_SOURCE)
            field_paths.append("allowed_source_revision_ids")

        graph_report = build_graph_quality_report(
            request.graph_snapshot,
            allowed_source_revision_ids=allowed,
        )
        loader_error_codes = {
            GraphIssueCode.UNAUTHORIZED_PROVENANCE,
            GraphIssueCode.MISSING_PROVENANCE,
        }
        if any(
            item.code in loader_error_codes and item.severity == "error"
            for item in graph_report.issues
        ):
            issue_codes.append(RootCauseIssueCode.UNAUTHORIZED_SOURCE)
            field_paths.append("graph_snapshot.loader_issues")

        if graph_report.status == GraphAuditStatus.FAIL:
            issue_codes.append(RootCauseIssueCode.UNAUTHORIZED_SOURCE)
            field_paths.append("graph_snapshot")
        elif graph_report.status == GraphAuditStatus.REVIEW_REQUIRED:
            issue_codes.append(RootCauseIssueCode.CONFLICTING_EVIDENCE)
            field_paths.append("graph_snapshot")

        hypotheses, traversal_issues = rank_root_cause_hypotheses(
            request.graph_snapshot,
            mapping_entry,
            target_concept_code=request.target_concept_code,
            limits=GraphTraversalLimits(max_depth=8, max_paths=8, max_nodes=48),
        )
        supported = [hypothesis for hypothesis in hypotheses if hypothesis.paths]

        path_budget_hit = any(
            item.code == GraphIssueCode.PATH_BUDGET_EXHAUSTED for item in traversal_issues
        )
        if path_budget_hit:
            issue_codes.append(RootCauseIssueCode.PATH_BUDGET_EXHAUSTED)
            field_paths.append("graph_snapshot.traversal")

        if not supported:
            issue_codes.append(RootCauseIssueCode.NO_PREREQUISITE_PATH)
            field_paths.append("hypotheses")
            verdict = RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE
        elif len(supported) >= 2 and supported[0].support_score == supported[1].support_score:
            issue_codes.append(RootCauseIssueCode.AMBIGUOUS_PATH)
            verdict = RootCauseVerdictStatus.REVIEW_REQUIRED
        elif path_budget_hit:
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
            hypotheses=supported,
            mapping_version=mapping.version,
            graph_snapshot_id=request.graph_snapshot.snapshot_id,
            graph_checksum=request.graph_snapshot.checksum,
            audit_ref=audit_ref,
            metadata_json={
                "disclaimer": (
                    "Hypotheses describe possible prerequisite mechanisms; "
                    "not demonstrated learner mastery."
                ),
                "graph_audit_status": graph_report.status.value,
                "audit_fingerprint": audit_ref,
            },
        )
