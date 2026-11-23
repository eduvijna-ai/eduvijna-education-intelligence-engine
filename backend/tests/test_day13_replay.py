from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.constants import CLAT_PACK_CODE
from app.cuet_clat.contracts import ClatPaperPlanRequest
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, IssueCode, PlanVerdict
from app.cuet_clat.replay_store import ReplayStore


def test_replay_returns_same_checksum_without_regeneration() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        replay_idempotency_key="demo-replay-1",
    )
    first = planner.plan(req)
    second = planner.plan(req)
    assert first.verdict == PlanVerdict.PASS
    assert second.checksum == first.checksum
    assert planner.synthetic_generation_count == 1


def test_stale_replay_on_trust_change() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        replay_idempotency_key="demo-replay-2",
        academic_year="2027",
    )
    planner.plan(req)
    stale = planner.plan(req.model_copy(update={"academic_year": "2026"}))
    assert stale.verdict == PlanVerdict.FAIL
    assert IssueCode.STALE_REPLAY in stale.issue_codes