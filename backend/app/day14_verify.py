"""Day 14 verification harness (D14-34)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.ca_imat_eapcet.authority import (
    resolve_ca_authority,
    resolve_eapcet_authority,
    resolve_imat_authority,
)
from app.ca_imat_eapcet.ca_descriptive import demo_descriptive_contracts, validate_descriptive_item
from app.ca_imat_eapcet.ca_planner import CaFoundationPlanner
from app.ca_imat_eapcet.constants import (
    CA_FOUNDATION_PACK_CODE,
    EAPCET_PACK_CODE,
    EAPCET_TOTAL_QUESTIONS,
    IMAT_PACK_CODE,
    IMAT_TOTAL_QUESTIONS,
)
from app.ca_imat_eapcet.contracts import (
    AllocateRequest,
    CaPaperPlanRequest,
    EapcetPaperPlanRequest,
    ImatPaperPlanRequest,
)
from app.ca_imat_eapcet.eapcet_planner import EapcetPaperPlanner
from app.ca_imat_eapcet.enums import (
    Day14ProfileKind,
    Day14SourceTrustMode,
    EapcetStream,
    PlanVerdict,
)
from app.ca_imat_eapcet.exam_profile import ensure_synthetic_demo_versions
from app.ca_imat_eapcet.extensibility_proof import build_extensibility_proof
from app.ca_imat_eapcet.governance import build_day14_governance_record
from app.ca_imat_eapcet.imat_planner import ImatPaperPlanner
from app.ca_imat_eapcet.imat_solver_check import independent_imat_answer_check
from app.ca_imat_eapcet.practice_service import Day14PracticeService
from app.ca_imat_eapcet.scope_ledger import load_repo_scope_counts
from app.ca_imat_eapcet.source_registry import build_source_registry_snapshot
from app.ca_imat_eapcet.validation_bridge import day6_bridge_status, day9_day10_bridge_status
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.verification.candidate_revision import RevisionEvidence, resolve_revision_evidence


def build_verification_report(
    session: Session,
    *,
    revision: RevisionEvidence,
) -> dict[str, object]:
    if revision.evidence_error or not revision.sha_aligned:
        return _revision_failure_report(revision)

    practice = Day14PracticeService()
    ca_obj = practice.allocate(
        AllocateRequest(
            exam_pack_code=CA_FOUNDATION_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            paper_or_section="paper3_quantitative_aptitude",
            requested_count=10,
            session_code="jan2027",
        )
    )

    ca_planner = CaFoundationPlanner()
    ca_plan = ca_planner.plan(
        CaPaperPlanRequest(
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            items_per_paper=5,
        )
    )

    imat_planner = ImatPaperPlanner()
    imat_plan = imat_planner.plan(
        ImatPaperPlanRequest(
            exam_pack_code=IMAT_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
        )
    )

    eapcet_eng = EapcetPaperPlanner()
    eng_plan = eapcet_eng.plan(
        EapcetPaperPlanRequest(
            exam_pack_code=EAPCET_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            stream=EapcetStream.ENGINEERING,
        )
    )
    ap_plan = eapcet_eng.plan(
        EapcetPaperPlanRequest(
            exam_pack_code=EAPCET_PACK_CODE,
            profile_kind=Day14ProfileKind.SYNTHETIC_DEMO,
            trust_mode=Day14SourceTrustMode.SYNTHETIC_FIXTURE,
            stream=EapcetStream.AGRICULTURE_PHARMACY,
        )
    )

    ca_future = resolve_ca_authority(
        profile_kind=Day14ProfileKind.CA_FUTURE_SESSION,
        session_code="future_jan2028",
    )
    imat_future = resolve_imat_authority(
        profile_kind=Day14ProfileKind.IMAT_FUTURE_YEAR,
        academic_year="2030",
    )
    eapcet_official = resolve_eapcet_authority(
        profile_kind=Day14ProfileKind.EAPCET_ENGINEERING_2026,
        stream=EapcetStream.ENGINEERING,
        exam_year="2026",
    )

    descriptive = demo_descriptive_contracts()
    desc_results = [validate_descriptive_item(d) for d in descriptive]

    ensure_synthetic_demo_versions(session)
    session.commit()

    ext = build_extensibility_proof()
    scope_counts = load_repo_scope_counts()

    imat_sample = imat_plan.delivered_count > 0
    solver_ok = True
    if imat_sample and ca_obj.questions:
        pass
    if imat_plan.delivered_count:
        from app.ca_imat_eapcet.synthetic_fixtures import build_imat_pool

        v, _ = independent_imat_answer_check(build_imat_pool()[0])
        solver_ok = v == PlanVerdict.PASS

    synthetic_ok = (
        ca_obj.verdict == PlanVerdict.PASS
        and ca_obj.delivered_count == 10
        and ca_plan.verdict == PlanVerdict.PASS
        and imat_plan.verdict == PlanVerdict.PASS
        and imat_plan.delivered_count == IMAT_TOTAL_QUESTIONS
        and eng_plan.verdict == PlanVerdict.PASS
        and eng_plan.delivered_count == EAPCET_TOTAL_QUESTIONS
        and ap_plan.delivered_count == EAPCET_TOTAL_QUESTIONS
        and all(v == PlanVerdict.PASS for v, _ in desc_results)
        and ext.verdict == PlanVerdict.PASS
        and scope_counts.get("TOTAL") == 36
        and solver_ok
        and revision.sha_aligned
    )

    report: dict[str, object] = {
        "ok": synthetic_ok,
        "governance": build_day14_governance_record(),
        "source_registry": build_source_registry_snapshot(session),
        "synthetic_fixture_pass": synthetic_ok,
        "ca_icai_curator_approved": False,
        "imat_decree_curator_approved": False,
        "eapcet_official_curator_approved": False,
        "scope_ledger_counts": scope_counts,
        "ca_objective_10": ca_obj.model_dump(),
        "ca_four_paper_plan": {
            "verdict": ca_plan.verdict.value,
            "paper_count": len(ca_plan.papers),
            "total_marks": ca_plan.total_marks,
        },
        "imat_full_paper": {
            "verdict": imat_plan.verdict.value,
            "delivered": imat_plan.delivered_count,
            "decimal_total_marks": imat_plan.decimal_total_marks,
            "sections": imat_plan.sections,
        },
        "eapcet_engineering": {
            "verdict": eng_plan.verdict.value,
            "section_counts": eng_plan.section_counts,
            "duration_minutes": eng_plan.duration_minutes,
        },
        "eapcet_agriculture_pharmacy": {
            "verdict": ap_plan.verdict.value,
            "section_counts": ap_plan.section_counts,
        },
        "authority_gates": {
            "ca_future": ca_future.verdict.value if ca_future.verdict else None,
            "imat_future": imat_future.verdict.value if imat_future.verdict else None,
            "eapcet_official": eapcet_official.verdict.value if eapcet_official.verdict else None,
        },
        "descriptive_contracts": {
            "count": len(descriptive),
            "all_pass": all(v == PlanVerdict.PASS for v, _ in desc_results),
            "automated_grading_claimed": False,
        },
        "extensibility_proof": ext.model_dump(),
        "validation_bridge": {
            "day6": day6_bridge_status(),
            "day9_day10": day9_day10_bridge_status(),
        },
        "trust_separation": {
            "synthetic": Day14SourceTrustMode.SYNTHETIC_FIXTURE.value,
            "ca_reference": Day14SourceTrustMode.CA_ICAI_REFERENCE.value,
            "imat_decree": Day14SourceTrustMode.IMAT_DM1005_2026.value,
            "eapcet_official": Day14SourceTrustMode.EAPCET_OFFICIAL_2026.value,
        },
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "anythingllm_live": "NOT_RUN",
            "full_historical_pytest": "NOT_RUN",
            "d14_36_founder_signoff": "NOT_STARTED",
            "migration_0021_blocker": "DEFERRED",
        },
    }
    report.update(revision.as_report_fields())
    return report


def _revision_failure_report(revision: RevisionEvidence) -> dict[str, object]:
    try:
        scope_counts = load_repo_scope_counts()
    except Exception:  # noqa: BLE001
        scope_counts = {"TOTAL": 0, "PARTIAL": 0, "SOURCE_PENDING": 0, "NOT_STARTED": 0}
    return {
        "ok": False,
        "synthetic_fixture_pass": False,
        "failure_reason": revision.evidence_error or "SHA_ALIGNMENT_FAILED",
        "scope_ledger_counts": scope_counts,
        **revision.as_report_fields(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 14 verification harness")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    revision = resolve_revision_evidence(cwd=Path(__file__).resolve().parents[1])

    try:
        engine = create_engine("sqlite:///:memory:")
        enable_sqlite_foreign_keys(engine)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            report = build_verification_report(session, revision=revision)
    except Exception as exc:  # noqa: BLE001
        report = {
            "ok": False,
            "failure_reason": f"verification_exception:{type(exc).__name__}",
            **revision.as_report_fields(),
        }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Day 14 verification:", "PASS" if report.get("ok") else "FAIL")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())