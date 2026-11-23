"""R03-A/B/C residual repair tests."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.constants import (
    CLAT_PACK_CODE,
    CUET_MARK_CORRECT,
    CUET_MARK_INCORRECT,
    CUET_PACK_CODE,
    MATHEMATICS_DOMAIN,
)
from app.cuet_clat.contracts import (
    ClatPaperPlanRequest,
    ClatPaperPlanResult,
    CuetPracticeRequest,
    CuetSingleTestRequest,
    PracticeQuestionRef,
)
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.practice_service import CuetPracticeService
from app.cuet_clat.replay_store import ReplayStore
from app.cuet_clat.synthetic_fixtures import SyntheticFixturePool, build_cuet_math_pool


def _cuet_practice(**kwargs: object) -> CuetPracticeRequest:
    base = dict(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        requested_count=10,
        medium_code="english",
        academic_year="2026",
    )
    base.update(kwargs)
    return CuetPracticeRequest(**base)  # type: ignore[arg-type]


def _cuet_single(**kwargs: object) -> CuetSingleTestRequest:
    base = dict(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        medium_code="english",
        academic_year="2026",
    )
    base.update(kwargs)
    return CuetSingleTestRequest(**base)  # type: ignore[arg-type]


def test_r03a_cuet_wrong_year_2025_rejected() -> None:
    svc = CuetPracticeService()
    for method in (
        svc.allocate_practice(_cuet_practice(academic_year="2025")),
        svc.assemble_single_test(_cuet_single(academic_year="2025")),
    ):
        assert method.verdict is not PlanVerdict.PASS
        assert IssueCode.WRONG_YEAR in method.issue_codes
        assert len(method.questions) == 0


def test_r03a_cuet_2027_still_not_verified() -> None:
    svc = CuetPracticeService()
    result = svc.allocate_practice(
        _cuet_practice(
            academic_year="2027",
            profile_kind=CuetClatProfileKind.CUET_CANDIDATE_2027,
            trust_mode=CuetClatSourceTrustMode.CUET_2027_NOT_VERIFIED,
        )
    )
    assert result.verdict == PlanVerdict.OFFICIAL_NOT_VERIFIED
    assert result.questions == []


def test_r03a_cuet_2026_positive_unchanged() -> None:
    svc = CuetPracticeService()
    ten = svc.allocate_practice(_cuet_practice())
    fifty = svc.assemble_single_test(_cuet_single())
    assert ten.verdict == PlanVerdict.PASS and ten.delivered_count == 10
    assert fifty.verdict == PlanVerdict.PASS and fifty.question_count == 50


def test_r03a_clat_wrong_synthetic_year() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2025",
        )
    )
    assert plan.verdict != PlanVerdict.PASS
    assert IssueCode.WRONG_YEAR in plan.issue_codes
    assert plan.questions == []


def test_r03a_clat_2027_synthetic_still_passes() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2027",
        )
    )
    assert plan.verdict == PlanVerdict.PASS
    assert plan.total_questions == 120


def test_r03b_mixed_pool_math10_no_leak() -> None:
    items = list(build_cuet_math_pool().cuet_math_items[:9])
    items[4] = PracticeQuestionRef(
        question_id="physics_intruder",
        subject_code="domain_physics",
        fingerprint="phys",
        correct_key="A",
        marks_if_correct=CUET_MARK_CORRECT,
        marks_if_incorrect=CUET_MARK_INCORRECT,
    )
    svc = CuetPracticeService(fixture_pool=SyntheticFixturePool(tuple(items), "mixed9"))
    result = svc.allocate_practice(_cuet_practice())
    assert result.verdict is not PlanVerdict.SHORTAGE
    assert result.verdict is not PlanVerdict.PASS
    assert IssueCode.WRONG_SUBJECT in result.issue_codes
    assert result.delivered_count == 0
    assert result.questions == []


def test_r03b_mixed_pool_math50_no_leak() -> None:
    items = list(build_cuet_math_pool().cuet_math_items[:49])
    items[0] = PracticeQuestionRef(
        question_id="physics_intruder50",
        subject_code="domain_physics",
        fingerprint="phys50",
        correct_key="A",
        marks_if_correct=CUET_MARK_CORRECT,
        marks_if_incorrect=CUET_MARK_INCORRECT,
    )
    svc = CuetPracticeService(fixture_pool=SyntheticFixturePool(tuple(items), "mixed49"))
    result = svc.assemble_single_test(_cuet_single())
    assert result.verdict is not PlanVerdict.SHORTAGE
    assert result.verdict is not PlanVerdict.PASS
    assert IssueCode.WRONG_SUBJECT in result.issue_codes
    assert result.question_count == 0


def test_r03b_honest_all_math_shortage_unchanged() -> None:
    items = tuple(build_cuet_math_pool().cuet_math_items[:9])
    svc = CuetPracticeService(fixture_pool=SyntheticFixturePool(items, "short9"))
    result = svc.allocate_practice(_cuet_practice())
    assert result.verdict == PlanVerdict.SHORTAGE
    assert result.delivered_count == 9


def test_r03c_concurrent_same_key_different_sections() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    barrier = threading.Barrier(2, timeout=5)
    key = "r03c-conflict"
    alloc_a = {
        "english": 24,
        "current_affairs_gk": 30,
        "legal_reasoning": 30,
        "logical_reasoning": 24,
        "quantitative_techniques": 12,
    }
    alloc_b = {
        "english": 25,
        "current_affairs_gk": 29,
        "legal_reasoning": 29,
        "logical_reasoning": 23,
        "quantitative_techniques": 14,
    }

    def run(overrides: dict[str, int]) -> ClatPaperPlanResult:
        barrier.wait(timeout=5)
        return planner.plan(
            ClatPaperPlanRequest(
                exam_pack_code=CLAT_PACK_CODE,
                profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
                trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
                academic_year="2027",
                replay_idempotency_key=key,
                section_overrides=overrides,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, alloc_a), pool.submit(run, alloc_b)]
        outcomes = [f.result(timeout=30) for f in as_completed(futures)]

    passes = [o for o in outcomes if o.verdict == PlanVerdict.PASS]
    stales = [o for o in outcomes if IssueCode.STALE_REPLAY in o.issue_codes]
    assert len(passes) == 1
    assert len(stales) == 1
    assert planner.synthetic_generation_count == 1


def test_r03c_concurrent_same_key_identical_requests() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    barrier = threading.Barrier(2, timeout=5)
    key = "r03c-identical"
    req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
        replay_idempotency_key=key,
    )

    def run() -> ClatPaperPlanResult:
        barrier.wait(timeout=5)
        return planner.plan(req)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run), pool.submit(run)]
        a, b = [f.result(timeout=30) for f in futures]

    assert a.verdict == PlanVerdict.PASS and b.verdict == PlanVerdict.PASS
    assert a.checksum == b.checksum
    assert planner.synthetic_generation_count == 1


def test_r03c_generation_failure_releases_reservation() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "r03c-abort"
    fail_req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
        replay_idempotency_key=key,
        metadata_json={"simulate_generation_failure": True},
    )
    failed = planner.plan(fail_req)
    assert failed.verdict != PlanVerdict.PASS

    ok = planner.plan(
        fail_req.model_copy(update={"metadata_json": {}}),
    )
    assert ok.verdict == PlanVerdict.PASS
    assert planner.synthetic_generation_count == 1