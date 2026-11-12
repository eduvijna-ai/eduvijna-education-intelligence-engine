from __future__ import annotations

import hashlib
import json

from app.jee_advanced.authority import resolve_profile_authority
from app.jee_advanced.constants import JEE_ADVANCED_PACK_CODE, PAPER_1_CODE, PAPER_2_CODE
from app.jee_advanced.contracts import AdvancedPaperPlanRequest, AdvancedPaperPlanResult
from app.jee_advanced.enums import AdvancedIssueCode, AdvancedPlanVerdict, AdvancedProfileKind
from app.jee_advanced.scope_guard import validate_exam_pack_scope
from app.jee_advanced.source_registry import reference_evidence_ready


class JeeAdvancedPaperPlanner:
    """D12-20..D12-22 planner shell — both papers and approved sources for reference."""

    def plan(self, request: AdvancedPaperPlanRequest) -> AdvancedPaperPlanResult:
        issues = list(validate_exam_pack_scope(request.exam_pack_code))
        if request.exam_pack_code != JEE_ADVANCED_PACK_CODE:
            issues.append(AdvancedIssueCode.WRONG_EXAM_PACK)

        authority = resolve_profile_authority(
            profile_kind=request.profile_kind,
            academic_year=request.academic_year,
            reference_sources_approved=reference_evidence_ready(),
        )

        if authority.verdict is not None:
            return AdvancedPaperPlanResult(
                verdict=authority.verdict,
                exam_pack_code=request.exam_pack_code,
                profile_kind=request.profile_kind,
                trust_mode=authority.trust_mode,
                academic_year=request.academic_year,
                paper_codes=request.paper_codes,
                issue_codes=[*issues, *authority.issue_codes],
                metadata_json={"planner_phase": "authority_gate"},
            )

        papers = request.paper_codes or [PAPER_1_CODE, PAPER_2_CODE]
        if request.simulate_full_pair and len(set(papers)) < 2:
            return AdvancedPaperPlanResult(
                verdict=AdvancedPlanVerdict.FAIL,
                exam_pack_code=request.exam_pack_code,
                profile_kind=request.profile_kind,
                trust_mode=authority.trust_mode,
                academic_year=request.academic_year,
                paper_codes=papers,
                issue_codes=[*issues, AdvancedIssueCode.SINGLE_PAPER_ONLY],
                metadata_json={"planner_phase": "pair_guard"},
            )

        is_reference = request.profile_kind is AdvancedProfileKind.REFERENCE_2026
        if is_reference and not authority.allow_reference_replica:
            return AdvancedPaperPlanResult(
                verdict=AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED,
                exam_pack_code=request.exam_pack_code,
                profile_kind=request.profile_kind,
                trust_mode=authority.trust_mode,
                academic_year=request.academic_year,
                paper_codes=papers,
                issue_codes=[
                    *issues,
                    AdvancedIssueCode.UNAPPROVED_SOURCE,
                    AdvancedIssueCode.BLUEPRINT_UNPINNED,
                ],
                metadata_json={"planner_phase": "reference_gate"},
            )

        checksums = {
            code: hashlib.sha256(
                json.dumps(
                    {
                        "paper": code,
                        "profile": request.profile_kind.value,
                        "trust": authority.trust_mode.value,
                        "synthetic_only": (
                            request.profile_kind is AdvancedProfileKind.SYNTHETIC_DEMO
                        ),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            for code in papers
        }

        verdict = (
            AdvancedPlanVerdict.PASS
            if request.profile_kind is AdvancedProfileKind.SYNTHETIC_DEMO
            else AdvancedPlanVerdict.REVIEW_REQUIRED
        )

        return AdvancedPaperPlanResult(
            verdict=verdict,
            exam_pack_code=request.exam_pack_code,
            profile_kind=request.profile_kind,
            trust_mode=authority.trust_mode,
            academic_year=request.academic_year,
            paper_codes=papers,
            issue_codes=issues,
            paper_checksums=checksums,
            origin_audit={"reference_sources_approved": reference_evidence_ready()},
            result_fingerprint=hashlib.sha256(
                json.dumps(checksums, sort_keys=True).encode()
            ).hexdigest(),
            metadata_json={"planner_phase": "synthetic_or_staged"},
        )
