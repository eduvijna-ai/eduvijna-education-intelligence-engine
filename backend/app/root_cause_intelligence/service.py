from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.trust_execution import TrustExecutionMode
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import GraphTraversalLimits
from app.prerequisite_intelligence.enums import (
    EdgeProvenanceClass,
    GraphAuditStatus,
    GraphIssueCode,
)
from app.prerequisite_intelligence.stable_ids import stable_audit_ref, stable_hypothesis_id
from app.root_cause_intelligence.contracts import (
    RootCauseDiagnosticRequest,
    RootCauseHypothesis,
    RootCauseResult,
)
from app.root_cause_intelligence.enums import (
    DEFAULT_ROOT_CAUSE_MAPPING_VERSION,
    RootCauseIssueCode,
    RootCauseVerdictStatus,
)
from app.root_cause_intelligence.mapping_authority import (
    apply_mapping_authority_overlay,
    authorized_mapping_revision_ids,
    mapping_entry_production_authorized,
)
from app.root_cause_intelligence.mapping_registry import load_root_cause_mapping
from app.root_cause_intelligence.preflight import run_root_cause_preflight
from app.root_cause_intelligence.ranking import (
    project_hypothesis_authorized_paths,
    rank_root_cause_hypotheses,
)
from app.root_cause_intelligence.trust_verify import (
    validate_graph_snapshot_attestation,
    verify_root_cause_trusted_context,
)
from app.root_cause_intelligence.trusted_validation import RootCauseTrustedValidationContext


class RootCauseIntelligenceService:
    def analyze(
        self,
        request: RootCauseDiagnosticRequest,
        *,
        trusted: RootCauseTrustedValidationContext | None = None,
        execution_mode: TrustExecutionMode = TrustExecutionMode.PRODUCTION,
        control_session: Session | None = None,
    ) -> RootCauseResult:
        preflight = run_root_cause_preflight(request, trusted=trusted)
        mapping = apply_mapping_authority_overlay(
            control_session,
            load_root_cause_mapping(DEFAULT_ROOT_CAUSE_MAPPING_VERSION),
        )
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

        if trusted is not None:
            trust_issues, trust_paths = verify_root_cause_trusted_context(
                trusted,
                request,
                execution_mode=execution_mode,
                control_session=control_session,
            )
            issue_codes.extend(trust_issues)
            field_paths.extend(trust_paths)

        scope_issues, scope_paths, scope_blocking = validate_graph_snapshot_attestation(
            request,
            execution_mode=execution_mode,
            control_session=control_session,
        )
        issue_codes.extend(scope_issues)
        field_paths.extend(scope_paths)

        trust_blocking = any(
            code
            in {
                RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION,
                RootCauseIssueCode.DAY9_TAG_REJECTED,
            }
            for code in issue_codes
        )
        if preflight.blocking or scope_blocking or trust_blocking:
            status = RootCauseVerdictStatus.FAIL
            if RootCauseIssueCode.CORRECT_OPTION_TAGGED in issue_codes:
                status = RootCauseVerdictStatus.REVIEW_REQUIRED
            elif RootCauseIssueCode.UNTRUSTED_TAG_VALIDATION in issue_codes:
                status = RootCauseVerdictStatus.REVIEW_REQUIRED
            elif RootCauseIssueCode.DAY9_TAG_REJECTED in issue_codes:
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
                hypotheses=[],
            )

        allowed = set(request.allowed_source_revision_ids or [])
        snapshot_allow = set(
            request.graph_snapshot.metadata_json.get("authorized_revision_ids") or []
        )
        if not allowed and snapshot_allow:
            issue_codes.append(RootCauseIssueCode.SNAPSHOT_ALLOWLIST_SPOOF)
            field_paths.append("graph_snapshot.metadata_json.authorized_revision_ids")

        has_sourced_edge = any(
            edge.source_revision_id
            and edge.provenance_class
            in {EdgeProvenanceClass.OFFICIAL, EdgeProvenanceClass.INFERRED}
            for edge in request.graph_snapshot.edges
        )
        if has_sourced_edge and not allowed:
            issue_codes.append(RootCauseIssueCode.UNAUTHORIZED_SOURCE)
            field_paths.append("allowed_source_revision_ids")

        production_mapping_ok = mapping_entry_production_authorized(
            control_session,
            mapping_entry,
            graph_scope=request.graph_snapshot.scope,
            allowed_option_revision_ids=allowed,
        )
        if execution_mode == TrustExecutionMode.PRODUCTION and not production_mapping_ok:
            issue_codes.append(RootCauseIssueCode.CONFLICTING_EVIDENCE)
            field_paths.append("mapping.synthetic")
            return RootCauseResult(
                item_id=request.item_id,
                option_key=request.option_key,
                misconception_code=request.misconception_code,
                verdict_status=RootCauseVerdictStatus.INSUFFICIENT_EVIDENCE,
                issue_codes=issue_codes,
                field_paths=field_paths,
                mapping_version=mapping.version,
                graph_snapshot_id=request.graph_snapshot.snapshot_id,
                graph_checksum=request.graph_snapshot.checksum,
                audit_ref=audit_ref,
                hypotheses=[],
            )

        graph_report = build_graph_quality_report(request.graph_snapshot)
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

        graph_blocking = (
            graph_report.status == GraphAuditStatus.FAIL
            or RootCauseIssueCode.SNAPSHOT_ALLOWLIST_SPOOF in issue_codes
            or (has_sourced_edge and not allowed)
        )
        if graph_blocking:
            issue_codes.append(RootCauseIssueCode.UNAUTHORIZED_SOURCE)
            field_paths.append("graph_snapshot")
        elif graph_report.status == GraphAuditStatus.REVIEW_REQUIRED:
            issue_codes.append(RootCauseIssueCode.CONFLICTING_EVIDENCE)
            field_paths.append("graph_snapshot")

        if graph_blocking:
            verdict = RootCauseVerdictStatus.FAIL
            if RootCauseIssueCode.CONFLICTING_EVIDENCE in issue_codes:
                verdict = RootCauseVerdictStatus.REVIEW_REQUIRED
            return RootCauseResult(
                item_id=request.item_id,
                option_key=request.option_key,
                misconception_code=request.misconception_code,
                verdict_status=verdict,
                issue_codes=issue_codes,
                field_paths=field_paths,
                hypotheses=[],
                mapping_version=mapping.version,
                graph_snapshot_id=request.graph_snapshot.snapshot_id,
                graph_checksum=request.graph_snapshot.checksum,
                audit_ref=audit_ref,
                metadata_json={
                    "graph_audit_status": graph_report.status.value,
                    "audit_fingerprint": audit_ref,
                },
            )

        hypotheses, traversal_issues = rank_root_cause_hypotheses(
            request.graph_snapshot,
            mapping_entry,
            target_concept_code=request.target_concept_code,
            limits=GraphTraversalLimits(max_depth=8, max_paths=8, max_nodes=48),
        )
        mapping_sources = authorized_mapping_revision_ids(mapping_entry, allowed)
        supported: list[RootCauseHypothesis] = []
        for hypothesis in hypotheses:
            projected = project_hypothesis_authorized_paths(
                request.graph_snapshot,
                hypothesis,
                allowed,
                mapping_sources,
            )
            if projected is not None:
                supported.append(projected)
        supported.sort(
            key=lambda item: (-item.support_score, item.rank, item.concept_code)
        )
        reranked_supported: list[RootCauseHypothesis] = []
        for index, hypothesis in enumerate(supported, start=1):
            reranked_supported.append(
                hypothesis.model_copy(
                    update={
                        "rank": index,
                        "hypothesis_id": stable_hypothesis_id(
                            request.graph_snapshot.checksum,
                            request.misconception_code,
                            hypothesis.concept_code,
                            index,
                        ),
                    }
                )
            )
        supported = reranked_supported

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
