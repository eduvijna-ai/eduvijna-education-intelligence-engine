from __future__ import annotations

import hashlib
import json

from app.cuet_clat.authority import resolve_cuet_authority
from app.cuet_clat.constants import (
    CUET_MARK_CORRECT,
    CUET_MARK_INCORRECT,
    CUET_MINUTES_PER_TEST,
    CUET_QUESTIONS_PER_TEST,
)
from app.cuet_clat.contracts import (
    CuetPracticeRequest,
    CuetPracticeResult,
    CuetSingleTestRequest,
    CuetSingleTestResult,
    PracticeQuestionRef,
)
from app.cuet_clat.enums import CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.scope_guard import (
    validate_cuet_math_practice,
    validate_cuet_medium,
    validate_cuet_pack,
    validate_cuet_subject,
)
from app.cuet_clat.synthetic_fixtures import SyntheticFixturePool, build_cuet_math_pool
from app.cuet_clat.trust_guard import validate_trust_coherence


class CuetPracticeService:
    """D13-12/13: exact-count CUET practice and single-test 50 MCQ assembly."""

    def __init__(self, *, fixture_pool: SyntheticFixturePool | None = None) -> None:
        self._pool = fixture_pool or build_cuet_math_pool()

    def allocate_practice(self, request: CuetPracticeRequest) -> CuetPracticeResult:
        issues = list(validate_cuet_pack(request.exam_pack_code))
        issues.extend(validate_cuet_subject(request.test_subject_code))
        issues.extend(validate_cuet_math_practice(request.test_subject_code))
        issues.extend(validate_cuet_medium(request.medium_code))
        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                academic_year=request.academic_year,
                exam_family="cuet",
            )
        )

        authority = resolve_cuet_authority(
            profile_kind=request.profile_kind,
            academic_year=request.academic_year,
        )
        if authority.verdict is not None:
            return self._shortage(
                request,
                verdict=authority.verdict,
                issues=[*issues, *authority.issue_codes],
            )

        if request.trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
            return self._shortage(
                request,
                verdict=PlanVerdict.SOURCE_PENDING,
                issues=[*issues, IssueCode.UNAPPROVED_SOURCE],
            )

        if request.requested_count <= 0:
            return self._shortage(
                request,
                verdict=PlanVerdict.FAIL,
                issues=[*issues, IssueCode.CUET_COUNT_MISMATCH],
            )

        pool = self._pool.cuet_math_items
        if len(pool) < request.requested_count:
            return self._shortage(
                request,
                verdict=PlanVerdict.SHORTAGE,
                issues=[*issues, IssueCode.CUET_COUNT_MISMATCH],
                delivered=list(pool),
            )

        delivered = list(pool[: request.requested_count])
        return CuetPracticeResult(
            verdict=PlanVerdict.PASS,
            requested_count=request.requested_count,
            delivered_count=len(delivered),
            questions=delivered,
            issue_codes=issues,
            checksum=_checksum(delivered),
            metadata_json={"demonstration_only": True, "trust_mode": request.trust_mode.value},
        )

    def assemble_single_test(self, request: CuetSingleTestRequest) -> CuetSingleTestResult:
        issues = list(validate_cuet_pack(request.exam_pack_code))
        issues.extend(validate_cuet_subject(request.test_subject_code))
        issues.extend(validate_cuet_medium(request.medium_code))
        issues.extend(
            validate_trust_coherence(
                profile_kind=request.profile_kind,
                trust_mode=request.trust_mode,
                academic_year=request.academic_year,
                exam_family="cuet",
            )
        )

        authority = resolve_cuet_authority(
            profile_kind=request.profile_kind,
            academic_year=request.academic_year,
        )
        if authority.verdict is not None:
            return CuetSingleTestResult(
                verdict=authority.verdict,
                question_count=0,
                duration_minutes=CUET_MINUTES_PER_TEST,
                marks_correct=CUET_MARK_CORRECT,
                marks_incorrect=CUET_MARK_INCORRECT,
                questions=[],
                issue_codes=[*issues, *authority.issue_codes],
                checksum="",
                metadata_json={"demonstration_only": True},
            )

        if request.trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
            return CuetSingleTestResult(
                verdict=PlanVerdict.NOT_READY,
                question_count=0,
                duration_minutes=CUET_MINUTES_PER_TEST,
                marks_correct=CUET_MARK_CORRECT,
                marks_incorrect=CUET_MARK_INCORRECT,
                questions=[],
                issue_codes=[*issues, IssueCode.UNAPPROVED_SOURCE],
                checksum="",
                metadata_json={"demonstration_only": False},
            )

        forced_count = request.metadata_json.get("forced_question_count")
        target = CUET_QUESTIONS_PER_TEST
        if isinstance(forced_count, int):
            target = forced_count
        elif isinstance(forced_count, str) and forced_count.isdigit():
            target = int(forced_count)

        pool = self._pool.cuet_math_items
        if target != CUET_QUESTIONS_PER_TEST:
            return CuetSingleTestResult(
                verdict=PlanVerdict.FAIL,
                question_count=target,
                duration_minutes=CUET_MINUTES_PER_TEST,
                marks_correct=CUET_MARK_CORRECT,
                marks_incorrect=CUET_MARK_INCORRECT,
                questions=[],
                issue_codes=[*issues, IssueCode.CUET_COUNT_MISMATCH],
                checksum="",
                metadata_json={"demonstration_only": True},
            )

        if len(pool) < target:
            return CuetSingleTestResult(
                verdict=PlanVerdict.SHORTAGE,
                question_count=len(pool),
                duration_minutes=CUET_MINUTES_PER_TEST,
                marks_correct=CUET_MARK_CORRECT,
                marks_incorrect=CUET_MARK_INCORRECT,
                questions=list(pool),
                issue_codes=[*issues, IssueCode.CUET_COUNT_MISMATCH],
                checksum=_checksum(list(pool)),
                metadata_json={"demonstration_only": True},
            )

        delivered = list(pool[:target])
        return CuetSingleTestResult(
            verdict=PlanVerdict.PASS,
            question_count=len(delivered),
            duration_minutes=CUET_MINUTES_PER_TEST,
            marks_correct=CUET_MARK_CORRECT,
            marks_incorrect=CUET_MARK_INCORRECT,
            questions=delivered,
            issue_codes=issues,
            checksum=_checksum(delivered),
            metadata_json={
                "demonstration_only": True,
                "paper_scoring_profile": "+5/-1",
            },
        )

    def _shortage(
        self,
        request: CuetPracticeRequest,
        *,
        verdict: PlanVerdict,
        issues: list[IssueCode],
        delivered: list[PracticeQuestionRef] | None = None,
    ) -> CuetPracticeResult:
        delivered = delivered or []
        return CuetPracticeResult(
            verdict=verdict,
            requested_count=request.requested_count,
            delivered_count=len(delivered),
            questions=delivered,
            issue_codes=issues,
            checksum=_checksum(delivered) if delivered else "",
            metadata_json={"demonstration_only": verdict is PlanVerdict.PASS},
        )


def _checksum(questions: list[PracticeQuestionRef]) -> str:
    payload = json.dumps([q.model_dump() for q in questions], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:40]