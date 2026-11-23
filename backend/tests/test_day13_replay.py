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
        academic_year="2027",
        replay_idempotency_key="demo-replay-1",
    )
    first = planner.plan(req)
    second = planner.plan(req)
    assert first.verdict == PlanVerdict.PASS
    assert second.checksum == first.checksum
    assert planner.synthetic_generation_count == 1


def test_stale_replay_on_tenant_change() -> None:
    store = ReplayStore()
    planner = ClatPaperPlanner(replay_store=store)
    req = ClatPaperPlanRequest(
        exam_pack_code=CLAT_PACK_CODE,
        profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
        trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
        replay_idempotency_key="demo-replay-2",
        academic_year="2027",
        organization_id="org-1",
        metadata_json={"tenant_scoped": True},
    )
    planner.plan(req)
    stale = planner.plan(req.model_copy(update={"organization_id": "org-2"}))
    assert stale.verdict == PlanVerdict.FAIL
    assert IssueCode.STALE_REPLAY in stale.issue_codes