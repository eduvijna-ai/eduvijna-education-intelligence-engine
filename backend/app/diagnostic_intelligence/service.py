from __future__ import annotations

from app.diagnostic_intelligence.contracts import (
    DiagnosticAuthoringRequest,
    DiagnosticVerdict,
    DistractorDiagnosticResult,
    OptionDiagnosticTag,
)
from app.diagnostic_intelligence.correct_option_guard import correct_option_integrity_issues
from app.diagnostic_intelligence.eligibility import diagnostic_eligibility
from app.diagnostic_intelligence.enums import DiagnosticIssueCode, DiagnosticValidationStatus
from app.diagnostic_intelligence.integration.day6_authority import day6_blocking_for_item
from app.diagnostic_intelligence.validators import (
    validate_curriculum_scope,
    validate_distinctness,
    validate_evidence_refs,
    validate_factual_incorrectness,
    validate_plausibility,
    validate_signal_alignment,
)
from app.diagnostic_intelligence.validators.result_integrity import (
    canonical_option_text,
    validate_result_integrity,
)
from app.diagnostic_intelligence.verdict import build_diagnostic_verdict
from app.education_intelligence.service import EducationIntelligenceValidationService
from app.orchestration.contracts import DraftQuestionItem, ResolvedScope, SolverResult


class DiagnosticIntelligenceService:
    """Framework-independent diagnostic distractor intelligence (D9-02)."""

    def __init__(
        self,
        education_service: EducationIntelligenceValidationService | None = None,
    ) -> None:
        self.education_service = education_service

    def validate_result(
        self,
        request: DiagnosticAuthoringRequest,
        result: DistractorDiagnosticResult,
        *,
        scope: ResolvedScope | None = None,
        request_marks: float | None = None,
        draft_item: DraftQuestionItem | None = None,
        candidate_codes: set[str] | None = None,
        solver: SolverResult | None = None,
    ) -> DiagnosticVerdict:
        allowed_codes = candidate_codes or set()
        eligible, status, _reason = diagnostic_eligibility(request.item)
        if not eligible:
            return DiagnosticVerdict(
                item_id=request.item.item_id,
                status=status,
                issue_codes=[_reason] if _reason else [],
                blocking=status == DiagnosticValidationStatus.REJECT,
                repairable=status == DiagnosticValidationStatus.REPAIR,
                review_required=status == DiagnosticValidationStatus.REVIEW_REQUIRED,
            )

        item_level: list[str] = list(validate_result_integrity(request, result))
        item_level.extend(correct_option_integrity_issues(result.option_tags))
        if item_level:
            return build_diagnostic_verdict(request.item.item_id, {}, item_level)

        if self.education_service is not None and scope is not None and draft_item is not None:
            item_level.extend(
                day6_blocking_for_item(
                    self.education_service,
                    draft_item,
                    scope,
                    request_marks=request_marks,
                )
            )

        option_issues: dict[str, list[str]] = {}
        for tag in result.option_tags:
            codes: list[str] = []
            text = canonical_option_text(request, tag)
            meta_text = str(tag.metadata_json.get("option_text") or "").strip()
            if meta_text and meta_text != text:
                codes.append(DiagnosticIssueCode.MALFORMED_MODEL_OUTPUT.value)
                codes.append("untrusted_option_text_metadata")
            codes.extend(
                validate_curriculum_scope(
                    request, tag, allowed_candidate_codes=allowed_codes
                )
            )
            codes.extend(validate_evidence_refs(request, tag))
            codes.extend(validate_signal_alignment(tag, text, stem_text=request.item.stem_text))
            codes.extend(validate_plausibility(tag, text))
            codes.extend(
                validate_factual_incorrectness(
                    request.item, tag, text, solver=solver
                )
            )
            if not tag.is_correct and not tag.misconception_code:
                codes.append("missing_diagnostic_tag")
            option_issues.setdefault(tag.option_key, []).extend(codes)

        distinct_issues, coverage = validate_distinctness(request.item.item_id, result.option_tags)
        item_level.extend(distinct_issues)
        result.coverage_summary = coverage

        return build_diagnostic_verdict(request.item.item_id, option_issues, item_level)

    def attach_validation_status(
        self, result: DistractorDiagnosticResult, verdict: DiagnosticVerdict
    ) -> DistractorDiagnosticResult:
        issue_by_option: dict[str, list[str]] = {}
        for item in verdict.items:
            if item.option_key:
                issue_by_option[item.option_key] = item.issue_codes
        updated_tags: list[OptionDiagnosticTag] = []
        for tag in result.option_tags:
            codes = issue_by_option.get(tag.option_key, [])
            status = DiagnosticValidationStatus.PASS
            if codes:
                status = (
                    DiagnosticValidationStatus.REPAIR
                    if verdict.repairable
                    else DiagnosticValidationStatus.REJECT
                    if verdict.blocking
                    else DiagnosticValidationStatus.REVIEW_REQUIRED
                )
            updated_tags.append(
                tag.model_copy(
                    update={
                        "issue_codes": codes,
                        "validation_status": status,
                    }
                )
            )
        result.option_tags = updated_tags
        result.aggregate_status = verdict.status
        result.errors = verdict.issue_codes if verdict.blocking else []
        result.warnings = verdict.issue_codes if verdict.review_required else []
        return result
