from __future__ import annotations

import hashlib
import json

from app.cuet_clat.authority import resolve_clat_authority
from app.cuet_clat.constants import (
    CLAT_SECTION_RANGES,
    CLAT_TOTAL_MINUTES,
    CLAT_TOTAL_QUESTIONS,
)
from app.cuet_clat.contracts import (
    ClatPaperPlanRequest,
    ClatPaperPlanResult,
    ClatSectionAllocation,
    PassageCluster,
    PracticeQuestionRef,
)
from app.cuet_clat.enums import CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.passage_clusters import build_passage_clusters
from app.cuet_clat.replay_store import ReplayStore
from app.cuet_clat.scope_guard import validate_clat_pack
from app.cuet_clat.section_allocator import allocate_clat_sections
from app.cuet_clat.synthetic_fixtures import build_clat_question
from app.cuet_clat.trust_guard import validate_trust_coherence


class ClatPaperPlanner:
    """D13-15..24: CLAT 120-question paper with section ranges and passage clusters."""

    def __init__(self, *, replay_store: ReplayStore | None = None) -> None:
        self._replay = replay_store or ReplayStore()

    def plan(self, request: ClatPaperPlanRequest) -> ClatPaperPlanResult:
        issues = list(validate_clat_pack(request.exam_pack_code))
        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                academic_year=request.academic_year,
                exam_family="clat",
            )
        )

        if request.metadata_json.get("forged_citation"):
            issues.append(IssueCode.FORGED_CITATION)
        if request.metadata_json.get("stale_current_affairs"):
            issues.append(IssueCode.STALE_CURRENT_AFFAIRS)
        if request.metadata_json.get("passage_answer_mismatch"):
            issues.append(IssueCode.PASSAGE_ANSWER_MISMATCH)

        authority = resolve_clat_authority(
            profile_kind=request.profile_kind,
            academic_year=request.academic_year,
        )

        if request.trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
            if authority.verdict is not None:
                return self._fail(request, [*issues, *authority.issue_codes], authority.verdict)

        forced_count = request.metadata_json.get("forced_total_questions")
        if isinstance(forced_count, int) and forced_count != CLAT_TOTAL_QUESTIONS:
            return self._fail(
                request,
                [*issues, IssueCode.CLAT_COUNT_MISMATCH],
                PlanVerdict.FAIL,
            )

        alloc = allocate_clat_sections(section_overrides=request.section_overrides)
        if alloc.verdict is not PlanVerdict.PASS:
            return self._fail(request, [*issues, *alloc.issue_codes], alloc.verdict)

        replay_key = request.replay_idempotency_key
        if replay_key:
            cached = self._replay.get(replay_key)
            if cached is not None:
                if request.metadata_json.get("invalidate_replay"):
                    return self._fail(
                        request,
                        [*issues, IssueCode.STALE_REPLAY],
                        PlanVerdict.FAIL,
                    )
                return ClatPaperPlanResult.model_validate(cached)

        all_questions = []
        all_clusters = []
        section_rows: list[ClatSectionAllocation] = []

        for section_code, count in alloc.allocations.items():
            section_qs = [
                build_clat_question(section_code=section_code, index=i, passage_id=None)
                for i in range(count)
            ]
            clusters = build_passage_clusters(section_code, section_qs)
            all_clusters.extend(clusters)
            all_questions.extend(section_qs)
            lo, hi = CLAT_SECTION_RANGES[section_code]
            section_rows.append(
                ClatSectionAllocation(
                    section_code=section_code,
                    question_count=count,
                    min_allowed=lo,
                    max_allowed=hi,
                )
            )

        if len(all_questions) != CLAT_TOTAL_QUESTIONS:
            return self._fail(
                request,
                [*issues, IssueCode.CLAT_COUNT_MISMATCH],
                PlanVerdict.FAIL,
            )

        ids = [q.question_id for q in all_questions]
        if len(set(ids)) != len(ids):
            return self._fail(request, [*issues, IssueCode.DUPLICATE_QUESTION], PlanVerdict.FAIL)

        if issues:
            return self._fail(request, issues, PlanVerdict.FAIL)

        result = ClatPaperPlanResult(
            verdict=PlanVerdict.PASS,
            total_questions=len(all_questions),
            duration_minutes=CLAT_TOTAL_MINUTES,
            section_allocations=section_rows,
            passage_clusters=all_clusters,
            questions=all_questions,
            issue_codes=[],
            checksum=_checksum(all_questions, all_clusters),
            metadata_json={
                "demonstration_only": (
                    request.trust_mode is CuetClatSourceTrustMode.SYNTHETIC_FIXTURE
                ),
                "scoring_profile": "+1/-0.25/0-blank",
                "current_affairs_rag_mode": "synthetic_fixture",
            },
        )

        if replay_key:
            self._replay.put(replay_key, result.model_dump())

        return result

    def _fail(
        self,
        request: ClatPaperPlanRequest,
        issues: list[IssueCode],
        verdict: PlanVerdict,
    ) -> ClatPaperPlanResult:
        _ = request
        return ClatPaperPlanResult(
            verdict=verdict,
            total_questions=0,
            duration_minutes=CLAT_TOTAL_MINUTES,
            section_allocations=[],
            passage_clusters=[],
            questions=[],
            issue_codes=issues,
            checksum="",
            metadata_json={"demonstration_only": True},
        )


def _checksum(
    questions: list[PracticeQuestionRef],
    clusters: list[PassageCluster],
) -> str:
    payload = json.dumps(
        {
            "q": [q.model_dump() for q in questions],
            "c": [c.model_dump() for c in clusters],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:40]