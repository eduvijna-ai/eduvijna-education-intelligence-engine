"""R04-A/B: missing academic year and replay owner exception recovery."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE, MATHEMATICS_DOMAIN
from app.cuet_clat.contracts import (
    ClatPaperPlanRequest,
    CuetPracticeRequest,
    CuetSingleTestRequest,
)
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.practice_service import CuetPracticeService
from app.cuet_clat.replay_store import ReplayStore


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


def _clat_plan(**kwargs: object) -> ClatPaperPlanRequest:
    base = dict(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
    )
    base.update(kwargs)
    return ClatPaperPlanRequest(**base)  # type: ignore[arg-type]


def test_r04a_cuet_omitted_year_rejects_both_entrypoints() -> None:
    svc = CuetPracticeService()
    omitted_practice = CuetPracticeRequest(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        requested_count=10,
        medium_code="english",
    )
    omitted_single = CuetSingleTestRequest(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        medium_code="english",
    )
    for result in (
        svc.allocate_practice(omitted_practice),
        svc.assemble_single_test(omitted_single),
    ):
        assert result.verdict is not PlanVerdict.PASS
        assert IssueCode.WRONG_YEAR in result.issue_codes
        assert result.questions == []


def test_r04a_cuet_blank_and_none_year_rejected() -> None:
    svc = CuetPracticeService()
    for year in (None, "", "   "):
        result = svc.allocate_practice(_cuet_practice(academic_year=year))
        assert result.verdict is not PlanVerdict.PASS
        assert IssueCode.WRONG_YEAR in result.issue_codes
        assert result.questions == []


def test_r04a_clat_omitted_year_no_pass() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        )
    )
    assert plan.verdict is not PlanVerdict.PASS
    assert IssueCode.WRONG_YEAR in plan.issue_codes
    assert plan.questions == []
    assert planner.synthetic_generation_count == 0


def test_r04a_explicit_years_still_pass() -> None:
    svc = CuetPracticeService()
    assert svc.allocate_practice(_cuet_practice()).verdict == PlanVerdict.PASS
    assert svc.assemble_single_test(_cuet_single()).verdict == PlanVerdict.PASS
    planner = ClatPaperPlanner()
    assert planner.plan(_clat_plan()).verdict == PlanVerdict.PASS


def test_r04b_value_error_releases_slot_and_retries() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "r04b-value-error"
    fail = planner.plan(
        _clat_plan(
            replay_idempotency_key=key,
            metadata_json={"simulate_value_error": True},
        )
    )
    assert fail.verdict != PlanVerdict.PASS
    started = time.monotonic()
    ok = planner.plan(_clat_plan(replay_idempotency_key=key))
    elapsed = time.monotonic() - started
    assert ok.verdict == PlanVerdict.PASS
    assert elapsed < 2.0
    assert planner.synthetic_generation_count == 1


def test_r04b_post_assembly_failure_cleans_slot() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "r04b-post-assembly"
    failed = planner.plan(
        _clat_plan(
            replay_idempotency_key=key,
            metadata_json={"simulate_post_assembly_failure": True},
        )
    )
    assert failed.verdict != PlanVerdict.PASS
    ok = planner.plan(_clat_plan(replay_idempotency_key=key))
    assert ok.verdict == PlanVerdict.PASS
    assert planner.synthetic_generation_count == 1


def test_r04b_publish_failure_cleans_slot() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "r04b-publish"
    failed = planner.plan(
        _clat_plan(
            replay_idempotency_key=key,
            metadata_json={"simulate_publish_failure": True},
        )
    )
    assert failed.verdict != PlanVerdict.PASS
    assert store.get(key) is None
    ok = planner.plan(_clat_plan(replay_idempotency_key=key))
    assert ok.verdict == PlanVerdict.PASS


def test_r04b_owner_pause_identical_concurrent_one_generation() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "r04b-pause-identical"
    pause = threading.Event()
    owner_started = threading.Event()
    req = _clat_plan(
        replay_idempotency_key=key,
        metadata_json={
            "owner_pause_event": pause,
            "owner_started_event": owner_started,
            "owner_pause_timeout": 5.0,
        },
    )

    def owner_plan() -> None:
        planner.plan(req)

    def waiter_plan() -> None:
        assert owner_started.wait(timeout=5.0)
        second = planner.plan(req)
        assert second.verdict == PlanVerdict.PASS

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner_future = pool.submit(owner_plan)
        waiter_future = pool.submit(waiter_plan)
        assert owner_started.wait(timeout=5.0)
        time.sleep(0.05)
        pause.set()
        owner_future.result(timeout=30)
        waiter_future.result(timeout=30)

    assert planner.synthetic_generation_count == 1


def test_r04b_owner_pause_conflict_returns_stale_replay() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "r04b-pause-conflict"
    pause = threading.Event()
    owner_started = threading.Event()
    base_req = _clat_plan(
        replay_idempotency_key=key,
        metadata_json={
            "owner_pause_event": pause,
            "owner_started_event": owner_started,
        },
    )
    conflict_alloc = {
        "english": 25,
        "current_affairs_gk": 29,
        "legal_reasoning": 29,
        "logical_reasoning": 23,
        "quantitative_techniques": 14,
    }

    def owner_plan() -> None:
        planner.plan(base_req)

    def conflict_plan() -> None:
        assert owner_started.wait(timeout=5.0)
        stale = planner.plan(base_req.model_copy(update={"section_overrides": conflict_alloc}))
        assert stale.verdict == PlanVerdict.FAIL
        assert IssueCode.STALE_REPLAY in stale.issue_codes

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner_future = pool.submit(owner_plan)
        conflict_future = pool.submit(conflict_plan)
        assert owner_started.wait(timeout=5.0)
        pause.set()
        owner_future.result(timeout=30)
        conflict_future.result(timeout=30)

    assert planner.synthetic_generation_count == 1


def test_r04b_wait_timeout_differs_from_stale_replay() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "r04b-wait-timeout"
    pause = threading.Event()
    owner_started = threading.Event()
    hold_req = _clat_plan(
        replay_idempotency_key=key,
        metadata_json={
            "owner_pause_event": pause,
            "owner_started_event": owner_started,
            "owner_pause_timeout": 10.0,
        },
    )

    def owner() -> None:
        planner.plan(hold_req)

    with ThreadPoolExecutor(max_workers=1) as pool:
        owner_future = pool.submit(owner)
        assert owner_started.wait(timeout=5.0)
        timed = planner.plan(
            hold_req.model_copy(
                update={
                    "metadata_json": {
                        "replay_wait_timeout": 0.05,
                    }
                }
            )
        )
        assert timed.verdict == PlanVerdict.REVIEW_REQUIRED
        assert IssueCode.REPLAY_WAIT_TIMEOUT in timed.issue_codes
        assert IssueCode.STALE_REPLAY not in timed.issue_codes
        pause.set()
        owner_future.result(timeout=30)

    retry = planner.plan(hold_req)
    assert retry.verdict == PlanVerdict.PASS
    assert planner.synthetic_generation_count == 1