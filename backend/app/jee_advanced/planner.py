from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.jee_advanced.authority import resolve_profile_authority
from app.jee_advanced.constants import JEE_ADVANCED_PACK_CODE, PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.contracts import AdvancedPaperPlanRequest, AdvancedPaperPlanResult
from app.jee_advanced.enums import (
    AdvancedIssueCode,
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.scope_guard import validate_exam_pack_scope
from app.jee_advanced.source_registry import reference_evidence_ready
from app.jee_advanced.synthetic_paper_assembly import (
    assemble_synthetic_paper_items,
    paper_checksum_from_items,
    validate_requested_counts,
)
from app.jee_advanced.trust_guard import validate_trust_coherence

_VALID_PAPER_CODES = frozenset({PAPER_1_CODE, PAPER_2_CODE})
_REQUIRED_PAIR = frozenset({PAPER_1_CODE, PAPER_2_CODE})


def _normalize_paper_codes(
    request: AdvancedPaperPlanRequest,
    issues: list[AdvancedIssueCode],
) -> list[str] | None:
    papers = list(request.paper_codes)
    if not papers:
        if request.simulate_full_pair:
            return [PAPER_1_CODE, PAPER_2_CODE]
        issues.append(AdvancedIssueCode.EMPTY_PAPER_PLAN)
        return None

    if len(papers) != len(set(papers)):
        issues.append(AdvancedIssueCode.DUPLICATE_PAPER_CODE)
        return papers

    for code in papers:
        if code not in _VALID_PAPER_CODES:
            issues.append(AdvancedIssueCode.INVALID_PAPER_CODE)

    if request.simulate_full_pair:
        paper_set = set(papers)
        if paper_set != _REQUIRED_PAIR or len(papers) != 2:
            issues.append(AdvancedIssueCode.SINGLE_PAPER_ONLY)

    return papers


class JeeAdvancedPaperPlanner:
    """D12-20..D12-22 planner — synthetic assembly with explicit demonstration item IDs."""

    def plan(
        self,
        request: AdvancedPaperPlanRequest,
        *,
        session: Session | None = None,
    ) -> AdvancedPaperPlanResult:
        issues = list(validate_exam_pack_scope(request.exam_pack_code))
        if request.exam_pack_code != JEE_ADVANCED_PACK_CODE:
            issues.append(AdvancedIssueCode.WRONG_EXAM_PACK)

        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                academic_year=request.academic_year,
            )
        )

        authority = resolve_profile_authority(
            profile_kind=request.profile_kind,
            academic_year=request.academic_year,
            session=session,
        )

        if authority.trust_mode != request.trust_mode and request.profile_kind in {
            AdvancedProfileKind.REFERENCE_2026,
            AdvancedProfileKind.CANDIDATE_2027,
        }:
            issues.append(AdvancedIssueCode.TRUST_PROFILE_MISMATCH)

        if authority.verdict is not None:
            return self._result(
                request,
                verdict=authority.verdict,
                trust_mode=authority.trust_mode,
                paper_codes=request.paper_codes,
                issues=[*issues, *authority.issue_codes],
                phase="authority_gate",
                session=session,
            )

        papers = _normalize_paper_codes(request, issues)
        if papers is None:
            return self._result(
                request,
                verdict=AdvancedPlanVerdict.FAIL,
                trust_mode=authority.trust_mode,
                paper_codes=[],
                issues=issues,
                phase="empty_paper_plan",
                session=session,
            )

        if issues:
            return self._result(
                request,
                verdict=AdvancedPlanVerdict.FAIL,
                trust_mode=authority.trust_mode,
                paper_codes=papers,
                issues=issues,
                phase="paper_validation",
                session=session,
            )

        is_reference = request.profile_kind is AdvancedProfileKind.REFERENCE_2026
        if is_reference and not authority.allow_reference_replica:
            return self._result(
                request,
                verdict=AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED,
                trust_mode=authority.trust_mode,
                paper_codes=papers,
                issues=[
                    AdvancedIssueCode.UNAPPROVED_SOURCE,
                    AdvancedIssueCode.BLUEPRINT_UNPINNED,
                ],
                phase="reference_gate",
                session=session,
            )

        if request.profile_kind is not AdvancedProfileKind.SYNTHETIC_DEMO:
            return self._result(
                request,
                verdict=AdvancedPlanVerdict.REVIEW_REQUIRED,
                trust_mode=authority.trust_mode,
                paper_codes=papers,
                issues=[],
                phase="non_synthetic_placeholder",
                session=session,
            )

        count_issues = validate_requested_counts(
            request.requested_counts,
            paper_codes=papers,
        )
        if count_issues:
            return self._result(
                request,
                verdict=AdvancedPlanVerdict.FAIL,
                trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
                paper_codes=papers,
                issues=count_issues,
                phase="invalid_requested_counts",
                session=session,
            )

        paper_items, assembly_issues, section_audit = assemble_synthetic_paper_items(
            paper_codes=papers,
            requested_counts=request.requested_counts or None,
        )
        item_id_map = {
            code: [item.question_id for item in refs] for code, refs in paper_items.items()
        }

        all_issues = list(assembly_issues)
        if all_issues or not all(item_id_map.values()):
            return self._result(
                request,
                verdict=AdvancedPlanVerdict.FAIL,
                trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
                paper_codes=papers,
                issues=all_issues,
                paper_item_ids=item_id_map,
                phase="synthetic_assembly_failed",
                session=session,
            )

        checksums = {
            code: paper_checksum_from_items(code, paper_items[code]) for code in papers
        }
        fingerprint = hashlib.sha256(
            json.dumps(checksums, sort_keys=True).encode()
        ).hexdigest()

        return self._result(
            request,
            verdict=AdvancedPlanVerdict.PASS,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            paper_codes=papers,
            issues=[],
            paper_item_ids=item_id_map,
            paper_checksums=checksums,
            fingerprint=fingerprint,
            phase="synthetic_assembled",
            extra_metadata={
                "assembly_mode": "synthetic_assembled_pcm",
                "demonstration_only": True,
                "section_audit": section_audit,
            },
            session=session,
        )

    @staticmethod
    def _result(
        request: AdvancedPaperPlanRequest,
        *,
        verdict: AdvancedPlanVerdict,
        trust_mode: JeeAdvancedSourceTrustMode,
        paper_codes: list[str],
        issues: list[AdvancedIssueCode],
        phase: str,
        session: Session | None = None,
        paper_item_ids: dict[str, list[str]] | None = None,
        paper_checksums: dict[str, str] | None = None,
        fingerprint: str | None = None,
        extra_metadata: dict[str, object] | None = None,
    ) -> AdvancedPaperPlanResult:
        if issues and verdict == AdvancedPlanVerdict.PASS:
            verdict = AdvancedPlanVerdict.FAIL

        metadata: dict[str, object] = {"planner_phase": phase}
        if extra_metadata:
            metadata.update(extra_metadata)

        return AdvancedPaperPlanResult(
            verdict=verdict,
            exam_pack_code=request.exam_pack_code,
            profile_kind=request.profile_kind,
            trust_mode=trust_mode,
            academic_year=request.academic_year,
            paper_codes=paper_codes,
            issue_codes=issues,
            paper_item_ids=paper_item_ids or {},
            paper_checksums=paper_checksums or {},
            origin_audit={
                "reference_sources_approved": reference_evidence_ready(session),
                "demonstration_only": metadata.get("demonstration_only", False),
            },
            result_fingerprint=fingerprint,
            metadata_json=metadata,
        )
