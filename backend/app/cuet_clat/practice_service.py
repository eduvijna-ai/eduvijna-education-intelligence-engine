from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

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
    resolve_academic_year_string,
    validate_academic_year_explicit,
)
from app.cuet_clat.cuet_persisted_selection import (
    persisted_target_count_for_single_test,
    select_validated_cuet_questions,
)
from app.cuet_clat.enums import CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.persisted_context import (
    PERSISTED_SELECTION_TOKEN,
    PersistedCuetSelectionContext,
    validate_persisted_practice_alignment,
    validate_persisted_single_test_alignment,
)
from app.cuet_clat.scope_guard import (
    validate_cuet_math_practice,
    validate_cuet_medium,
    validate_cuet_pack,
    validate_cuet_subject,
    validate_delivered_subject,
)
from app.cuet_clat.synthetic_fixtures import SyntheticFixturePool, build_cuet_math_pool
from app.cuet_clat.trust_guard import validate_trust_coherence

_COUNT_ISSUES = frozenset({IssueCode.CUET_COUNT_MISMATCH})


def cuet_scope_preflight_issues(
    *,
    exam_pack_code: str,
    test_subject_code: str,
    medium_code: str,
    profile_kind: object,
    trust_mode: object,
    academic_year: str,
) -> list[IssueCode]:
    """Shared deterministic scope/trust preflight for CUET practice entrypoints."""

    issues: list[IssueCode] = []
    issues.extend(validate_cuet_pack(exam_pack_code))
    issues.extend(validate_cuet_subject(test_subject_code))
    issues.extend(validate_cuet_math_practice(test_subject_code))
    issues.extend(validate_cuet_medium(medium_code))
    issues.extend(
        validate_trust_coherence(
            profile_kind=profile_kind,  # type: ignore[arg-type]
            trust_mode=trust_mode,  # type: ignore[arg-type]
            academic_year=academic_year,
            exam_family="cuet",
        )
    )
    return issues


def _scope_blocked(issues: list[IssueCode]) -> bool:
    return bool(issues) and not all(code in _COUNT_ISSUES for code in issues)


def _eligible_pool(
    pool: tuple[PracticeQuestionRef, ...],
    *,
    expected_subject: str,
) -> tuple[list[PracticeQuestionRef], list[IssueCode]]:
    subject_issues = validate_delivered_subject(
        expected_subject=expected_subject,
        question_subject_codes=[q.subject_code for q in pool],
    )
    if subject_issues:
        return [], subject_issues
    return list(pool), []


class CuetPracticeService:
    """D13-12/13: exact-count CUET practice and single-test 50 MCQ assembly."""

    def __init__(self, *, fixture_pool: SyntheticFixturePool | None = None) -> None:
        self._pool = fixture_pool or build_cuet_math_pool()

    def allocate_practice(
        self,
        request: CuetPracticeRequest,
        *,
        session: Session | None = None,
        persisted: PersistedCuetSelectionContext | None = None,
    ) -> CuetPracticeResult:
        year_issues = validate_academic_year_explicit(request)
        if year_issues:
            return self._reject_practice(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe(year_issues),
            )
        academic_year = resolve_academic_year_string(request)

        issues = cuet_scope_preflight_issues(
            exam_pack_code=request.exam_pack_code,
            test_subject_code=request.test_subject_code,
            medium_code=request.medium_code,
            profile_kind=request.profile_kind,
            trust_mode=request.trust_mode,
            academic_year=academic_year,
        )

        authority = resolve_cuet_authority(
            profile_kind=request.profile_kind,
            academic_year=academic_year,
        )
        if authority.verdict is not None:
            return self._reject_practice(
                request,
                verdict=authority.verdict,
                issues=_dedupe([*issues, *authority.issue_codes]),
            )

        if request.trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
            return self._reject_practice(
                request,
                verdict=PlanVerdict.SOURCE_PENDING,
                issues=_dedupe([*issues, IssueCode.UNAPPROVED_SOURCE]),
            )

        if _scope_blocked(issues):
            return self._reject_practice(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe(issues),
            )

        if request.requested_count <= 0:
            return self._reject_practice(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe([*issues, IssueCode.CUET_COUNT_MISMATCH]),
            )

        if persisted is not None:
            return self._allocate_persisted_practice(
                request,
                session=session,
                persisted=persisted,
                issues=issues,
            )

        eligible, subject_issues = _eligible_pool(
            self._pool.cuet_math_items,
            expected_subject=request.test_subject_code,
        )
        if subject_issues:
            return self._reject_practice(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe([*issues, *subject_issues]),
            )

        if len(eligible) < request.requested_count:
            return self._reject_practice(
                request,
                verdict=PlanVerdict.SHORTAGE,
                issues=_dedupe([*issues, IssueCode.CUET_COUNT_MISMATCH]),
                delivered=eligible,
                allow_partial=True,
            )

        delivered = eligible[: request.requested_count]

        return CuetPracticeResult(
            verdict=PlanVerdict.PASS,
            requested_count=request.requested_count,
            delivered_count=len(delivered),
            questions=delivered,
            issue_codes=[],
            checksum=_checksum(delivered),
            metadata_json={"demonstration_only": True, "trust_mode": request.trust_mode.value},
        )

    def assemble_single_test(
        self,
        request: CuetSingleTestRequest,
        *,
        session: Session | None = None,
        persisted: PersistedCuetSelectionContext | None = None,
    ) -> CuetSingleTestResult:
        year_issues = validate_academic_year_explicit(request)
        if year_issues:
            return self._reject_single_test(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe(year_issues),
            )
        academic_year = resolve_academic_year_string(request)

        issues = cuet_scope_preflight_issues(
            exam_pack_code=request.exam_pack_code,
            test_subject_code=request.test_subject_code,
            medium_code=request.medium_code,
            profile_kind=request.profile_kind,
            trust_mode=request.trust_mode,
            academic_year=academic_year,
        )

        authority = resolve_cuet_authority(
            profile_kind=request.profile_kind,
            academic_year=academic_year,
        )
        if authority.verdict is not None:
            return self._reject_single_test(
                request,
                verdict=authority.verdict,
                issues=_dedupe([*issues, *authority.issue_codes]),
            )

        if request.trust_mode is not CuetClatSourceTrustMode.SYNTHETIC_FIXTURE:
            return self._reject_single_test(
                request,
                verdict=PlanVerdict.NOT_READY,
                issues=_dedupe([*issues, IssueCode.UNAPPROVED_SOURCE]),
            )

        if _scope_blocked(issues):
            return self._reject_single_test(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe(issues),
            )

        if persisted is not None:
            return self._assemble_persisted_single_test(
                request,
                session=session,
                persisted=persisted,
                issues=issues,
            )

        forced_count = request.metadata_json.get("forced_question_count")
        target = CUET_QUESTIONS_PER_TEST
        if isinstance(forced_count, int):
            target = forced_count
        elif isinstance(forced_count, str) and forced_count.isdigit():
            target = int(forced_count)

        if target != CUET_QUESTIONS_PER_TEST:
            return self._reject_single_test(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe([*issues, IssueCode.CUET_COUNT_MISMATCH]),
            )

        eligible, subject_issues = _eligible_pool(
            self._pool.cuet_math_items,
            expected_subject=request.test_subject_code,
        )
        if subject_issues:
            return self._reject_single_test(
                request,
                verdict=PlanVerdict.FAIL,
                issues=_dedupe([*issues, *subject_issues]),
            )

        if len(eligible) < target:
            return self._reject_single_test(
                request,
                verdict=PlanVerdict.SHORTAGE,
                issues=_dedupe([IssueCode.CUET_COUNT_MISMATCH]),
                questions=eligible,
                allow_partial=True,
            )

        delivered = eligible[:target]

        return CuetSingleTestResult(
            verdict=PlanVerdict.PASS,
            question_count=len(delivered),
            duration_minutes=CUET_MINUTES_PER_TEST,
            marks_correct=CUET_MARK_CORRECT,
            marks_incorrect=CUET_MARK_INCORRECT,
            questions=delivered,
            issue_codes=[],
            checksum=_checksum(delivered),
            metadata_json={
                "demonstration_only": True,
                "paper_scoring_profile": "+5/-1",
            },
        )

    def _allocate_persisted_practice(
        self,
        request: CuetPracticeRequest,
        *,
        session: Session | None,
        persisted: PersistedCuetSelectionContext,
        issues: list[IssueCode],
    ) -> CuetPracticeResult:
        if session is None or persisted.selection_token != PERSISTED_SELECTION_TOKEN:
            return self._reject_practice(
                request,
                verdict=PlanVerdict.NOT_READY,
                issues=_dedupe([*issues, IssueCode.MISSING_PERSISTED_CONTEXT]),
            )
        align_issues, align_verdict = validate_persisted_practice_alignment(
            request, context=persisted, session=session
        )
        if align_verdict is not None:
            return self._reject_practice(
                request,
                verdict=align_verdict,
                issues=_dedupe([*issues, *align_issues]),
            )

        selected, select_issues, verdict = select_validated_cuet_questions(
            session,
            context=persisted,
            test_subject_code=request.test_subject_code,
            requested_count=request.requested_count,
        )
        if verdict is not PlanVerdict.PASS:
            return self._reject_practice(
                request,
                verdict=verdict,
                issues=_dedupe([*issues, *select_issues]),
            )
        return CuetPracticeResult(
            verdict=PlanVerdict.PASS,
            requested_count=request.requested_count,
            delivered_count=len(selected),
            questions=selected,
            issue_codes=[],
            checksum=_checksum(selected),
            metadata_json={
                "demonstration_only": False,
                "validated_persisted_synthetic": True,
                "synthetic_test_only": True,
                "trust_mode": request.trust_mode.value,
            },
        )

    def _assemble_persisted_single_test(
        self,
        request: CuetSingleTestRequest,
        *,
        session: Session | None,
        persisted: PersistedCuetSelectionContext,
        issues: list[IssueCode],
    ) -> CuetSingleTestResult:
        if session is None or persisted.selection_token != PERSISTED_SELECTION_TOKEN:
            return self._reject_single_test(
                request,
                verdict=PlanVerdict.NOT_READY,
                issues=_dedupe([*issues, IssueCode.MISSING_PERSISTED_CONTEXT]),
            )
        align_issues, align_verdict = validate_persisted_single_test_alignment(
            request, context=persisted, session=session
        )
        if align_verdict is not None:
            return self._reject_single_test(
                request,
                verdict=align_verdict,
                issues=_dedupe([*issues, *align_issues]),
            )
        target = persisted_target_count_for_single_test()
        selected, select_issues, verdict = select_validated_cuet_questions(
            session,
            context=persisted,
            test_subject_code=request.test_subject_code,
            requested_count=target,
        )
        if verdict is not PlanVerdict.PASS:
            return self._reject_single_test(
                request,
                verdict=verdict,
                issues=_dedupe([*issues, *select_issues]),
            )
        return CuetSingleTestResult(
            verdict=PlanVerdict.PASS,
            question_count=len(selected),
            duration_minutes=CUET_MINUTES_PER_TEST,
            marks_correct=CUET_MARK_CORRECT,
            marks_incorrect=CUET_MARK_INCORRECT,
            questions=selected,
            issue_codes=[],
            checksum=_checksum(selected),
            metadata_json={
                "demonstration_only": False,
                "validated_persisted_synthetic": True,
                "synthetic_test_only": True,
            },
        )

    def _reject_practice(
        self,
        request: CuetPracticeRequest,
        *,
        verdict: PlanVerdict,
        issues: list[IssueCode],
        delivered: list[PracticeQuestionRef] | None = None,
        allow_partial: bool = False,
    ) -> CuetPracticeResult:
        questions: list[PracticeQuestionRef] = []
        if allow_partial and verdict is PlanVerdict.SHORTAGE and delivered is not None:
            questions = list(delivered)
        return CuetPracticeResult(
            verdict=verdict,
            requested_count=request.requested_count,
            delivered_count=len(questions),
            questions=questions,
            issue_codes=issues,
            checksum=_checksum(questions) if questions else "",
            metadata_json={"demonstration_only": False},
        )

    def _reject_single_test(
        self,
        request: CuetSingleTestRequest,
        *,
        verdict: PlanVerdict,
        issues: list[IssueCode],
        questions: list[PracticeQuestionRef] | None = None,
        allow_partial: bool = False,
    ) -> CuetSingleTestResult:
        _ = request
        qs: list[PracticeQuestionRef] = []
        if allow_partial and verdict is PlanVerdict.SHORTAGE and questions is not None:
            qs = list(questions)
        return CuetSingleTestResult(
            verdict=verdict,
            question_count=len(qs),
            duration_minutes=CUET_MINUTES_PER_TEST,
            marks_correct=CUET_MARK_CORRECT,
            marks_incorrect=CUET_MARK_INCORRECT,
            questions=qs,
            issue_codes=issues,
            checksum=_checksum(qs) if qs else "",
            metadata_json={"demonstration_only": False},
        )


def _dedupe(issues: list[IssueCode]) -> list[IssueCode]:
    seen: set[IssueCode] = set()
    ordered: list[IssueCode] = []
    for code in issues:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def _checksum(questions: list[PracticeQuestionRef]) -> str:
    payload = json.dumps([q.model_dump() for q in questions], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:40]