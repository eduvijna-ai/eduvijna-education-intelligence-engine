"""F01/F02 mandatory negative and positive repair tests."""

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
    CuetPracticeRequest,
    CuetSingleTestRequest,
    PracticeQuestionRef,
)
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.practice_service import CuetPracticeService
from app.cuet_clat.replay_store import ReplayStore
from app.cuet_clat.synthetic_fixtures import SyntheticFixturePool, build_cuet_math_pool


def _synthetic_cuet_request(**overrides: object) -> CuetPracticeRequest:
    base = dict(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        requested_count=10,
        medium_code="english",
        academic_year="2026",
    )
    base.update(overrides)
    return CuetPracticeRequest(**base)  # type: ignore[arg-type]


def _synthetic_single_test(**overrides: object) -> CuetSingleTestRequest:
    base = dict(
        exam_pack_code=CUET_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        test_subject_code=MATHEMATICS_DOMAIN,
        medium_code="english",
        academic_year="2026",
    )
    base.update(overrides)
    return CuetSingleTestRequest(**base)  # type: ignore[arg-type]


def test_f01_wrong_pack_vetoes_practice_and_single_test() -> None:
    svc = CuetPracticeService()
    practice = svc.allocate_practice(_synthetic_cuet_request(exam_pack_code=CLAT_PACK_CODE))
    assert practice.verdict != PlanVerdict.PASS
    assert IssueCode.WRONG_EXAM_PACK in practice.issue_codes
    assert practice.questions == []

    single = svc.assemble_single_test(_synthetic_single_test(exam_pack_code=CLAT_PACK_CODE))
    assert single.verdict != PlanVerdict.PASS
    assert IssueCode.WRONG_EXAM_PACK in single.issue_codes
    assert single.questions == []


def test_f01_invalid_subjects_never_pass() -> None:
    svc = CuetPracticeService()
    for subject in ("jee_main", "invented", "domain_physics"):
        result = svc.allocate_practice(_synthetic_cuet_request(test_subject_code=subject))
        assert result.verdict != PlanVerdict.PASS
        assert result.questions == []
        assert IssueCode.WRONG_SUBJECT in result.issue_codes or IssueCode.JEE_MAIN_FALLBACK in (
            result.issue_codes
        )


def test_f01_unsupported_medium_vetoes_pass() -> None:
    svc = CuetPracticeService()
    result = svc.allocate_practice(_synthetic_cuet_request(medium_code="urdu"))
    assert result.verdict != PlanVerdict.PASS
    assert result.questions == []
    assert IssueCode.WRONG_MEDIUM in result.issue_codes


def test_f01_wrong_trust_combination_no_questions() -> None:
    svc = CuetPracticeService()
    result = svc.allocate_practice(
        CuetPracticeRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.CUET_HISTORICAL_2026,
            test_subject_code=MATHEMATICS_DOMAIN,
            requested_count=10,
            academic_year="2026",
        )
    )
    assert result.verdict != PlanVerdict.PASS
    assert result.questions == []
    assert IssueCode.UNAPPROVED_SOURCE in result.issue_codes


def test_f01_wrong_subject_in_pool_vetoes_pass() -> None:
    pool_items = list(build_cuet_math_pool().cuet_math_items)
    pool_items[0] = PracticeQuestionRef(
        question_id="bad_subj",
        subject_code="domain_physics",
        topic_code="algebra_basics",
        fingerprint="bad",
        correct_key="A",
        marks_if_correct=CUET_MARK_CORRECT,
        marks_if_incorrect=CUET_MARK_INCORRECT,
    )
    svc = CuetPracticeService(fixture_pool=SyntheticFixturePool(tuple(pool_items), "bad_pool"))
    result = svc.allocate_practice(_synthetic_cuet_request())
    assert result.verdict != PlanVerdict.PASS
    assert result.questions == []


def test_f01_shortage_only_when_scope_valid() -> None:
    small_pool = SyntheticFixturePool(
        tuple(build_cuet_math_pool().cuet_math_items[:9]), "small"
    )
    svc = CuetPracticeService(fixture_pool=small_pool)
    result = svc.allocate_practice(_synthetic_cuet_request(requested_count=10))
    assert result.verdict == PlanVerdict.SHORTAGE
    assert result.delivered_count == 9
    assert IssueCode.CUET_COUNT_MISMATCH in result.issue_codes

    invalid = svc.allocate_practice(_synthetic_cuet_request(medium_code="urdu", requested_count=10))
    assert invalid.verdict != PlanVerdict.SHORTAGE
    assert invalid.delivered_count == 0


def test_f01_positive_10_and_50_unchanged() -> None:
    svc = CuetPracticeService()
    ten = svc.allocate_practice(_synthetic_cuet_request())
    assert ten.verdict == PlanVerdict.PASS
    assert ten.delivered_count == 10
    assert ten.issue_codes == []

    fifty = svc.assemble_single_test(_synthetic_single_test())
    assert fifty.verdict == PlanVerdict.PASS
    assert fifty.question_count == 50
    assert fifty.issue_codes == []


def test_f02_replay_same_request_no_extra_generation() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
        replay_idempotency_key="f02-stable",
    )
    first = planner.plan(req)
    assert first.verdict == PlanVerdict.PASS
    assert planner.synthetic_generation_count == 1
    second = planner.plan(req)
    assert second.verdict == PlanVerdict.PASS
    assert second.checksum == first.checksum
    assert planner.synthetic_generation_count == 1


def test_f02_changed_section_override_stale_replay() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "f02-sections"
    base = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
        replay_idempotency_key=key,
    )
    original = planner.plan(base)
    assert original.verdict == PlanVerdict.PASS
    stored = store.get(key)
    assert stored is not None

    changed = base.model_copy(
        update={
            "section_overrides": {
                "english": 25,
                "current_affairs_gk": 29,
                "legal_reasoning": 29,
                "logical_reasoning": 23,
                "quantitative_techniques": 14,
            }
        }
    )
    stale = planner.plan(changed)
    assert stale.verdict == PlanVerdict.FAIL
    assert IssueCode.STALE_REPLAY in stale.issue_codes
    after = store.get(key)
    assert after is not None
    assert after.result_payload == stored.result_payload
    assert after.request_fingerprint == stored.request_fingerprint


def test_f02_changed_tenant_stale_replay() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "f02-tenant"
    req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
        replay_idempotency_key=key,
        organization_id="org-a",
        metadata_json={"tenant_scoped": True},
    )
    planner.plan(req)
    stale = planner.plan(req.model_copy(update={"organization_id": "org-b"}))
    assert stale.verdict == PlanVerdict.FAIL
    assert IssueCode.STALE_REPLAY in stale.issue_codes


def test_f02_review_flags_block_before_cached_pass() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    key = "f02-flags"
    base = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
        replay_idempotency_key=key,
    )
    planner.plan(base)
    for flag in ("forged_citation", "stale_current_affairs", "passage_answer_mismatch"):
        blocked = planner.plan(
            base.model_copy(update={"metadata_json": {flag: True}})
        )
        assert blocked.verdict == PlanVerdict.FAIL
        assert blocked.questions == []


def test_f02_clat_official_profile_with_synthetic_trust_fails() -> None:
    planner = ClatPaperPlanner()
    plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.CLAT_2027,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2027",
        )
    )
    assert plan.verdict != PlanVerdict.PASS
    assert plan.questions == []


def test_f02_new_process_has_no_replay_cache() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        academic_year="2027",
        replay_idempotency_key="f02-restart",
    )
    planner.plan(req)
    fresh = ClatPaperPlanner(replay_store=ReplayStore())
    again = fresh.plan(req)
    assert again.verdict == PlanVerdict.PASS
    assert fresh.synthetic_generation_count == 1