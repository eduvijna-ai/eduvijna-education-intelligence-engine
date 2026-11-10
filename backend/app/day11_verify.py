"""Founder Day 11 verification harness (D11-35)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.jee_main_exam_intelligence.constants import (
    CANDIDATE_PAPER1_TOTAL_QUESTIONS,
    JEE_MAIN_EXAM_PACK_CODE,
    JEE_MAIN_VERSION_2027,
)
from app.jee_main_exam_intelligence.enums import PaperPlanMode, PaperPlanVerdict
from app.jee_main_exam_intelligence.exam_catalogue import get_exam_version
from app.jee_main_exam_intelligence.fixtures import (
    build_official_replica_request,
    build_practice_algebra_ten_request,
    build_practice_math_ten_request,
    seed_day11_fixture_context,
    synthetic_activate_nta_sources_for_harness,
)
from app.jee_main_exam_intelligence.service import JeeMainExamIntelligenceService
from app.jee_main_exam_intelligence.source_authority import evaluate_official_pattern_authority


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2]
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _resolve_candidate_sha() -> str:
    explicit = os.environ.get("EDUVIJNA_CANDIDATE_SHA", "").strip()
    if explicit:
        return explicit
    return _git_head()


def build_verification_report(session: Session) -> dict[str, object]:
    candidate_sha, head_sha = _resolve_candidate_sha(), _git_head()
    sha_checks = {
        "candidate_sha_resolved": candidate_sha not in {"", "unknown"},
        "candidate_sha_matches_head": candidate_sha == head_sha,
    }

    service = JeeMainExamIntelligenceService()
    service.register_nta_candidate_sources(session)
    authority_before = service.evaluate_official_authority(
        session, exam_version_code=JEE_MAIN_VERSION_2027
    )

    ctx = seed_day11_fixture_context(session)
    session.commit()

    replica_fail = service.plan_paper(session, build_official_replica_request(ctx), persist=False)
    official_replica_blocked_unverified = (
        replica_fail.verdict == PaperPlanVerdict.FAIL
        and replica_fail.official_pattern_label == "official_pattern_not_verified"
    )

    synthetic_activate_nta_sources_for_harness(session, exam_version_id=ctx["exam_version_2027_id"])
    session.commit()
    authority_after = service.evaluate_official_authority(
        session, exam_version_code=JEE_MAIN_VERSION_2027
    )

    math_ten = service.plan_paper(session, build_practice_math_ten_request(ctx))
    algebra_ten = service.plan_paper(session, build_practice_algebra_ten_request(ctx))
    replica = service.plan_paper(session, build_official_replica_request(ctx))
    session.commit()

    version = get_exam_version(
        session,
        pack_code=JEE_MAIN_EXAM_PACK_CODE,
        version_code=JEE_MAIN_VERSION_2027,
    )
    status, _, _ = evaluate_official_pattern_authority(session, exam_version=version)

    checks = {
        **sha_checks,
        "nta_candidate_sources_registered": bool(authority_before.get("sources")),
        "official_replica_fail_closed_before_synthetic_activation": (
            official_replica_blocked_unverified
        ),
        "synthetic_harness_authority_verified": authority_after.get("status") == "verified",
        "practice_math_exactly_ten": (
            math_ten.verdict == PaperPlanVerdict.PASS and math_ten.actual_count == 10
        ),
        "practice_algebra_exactly_ten": (
            algebra_ten.verdict == PaperPlanVerdict.PASS and algebra_ten.actual_count == 10
        ),
        "synthetic_official_replica_seventy_five": (
            replica.verdict == PaperPlanVerdict.PASS
            and replica.actual_count == CANDIDATE_PAPER1_TOTAL_QUESTIONS
        ),
        "synthetic_official_pattern_label_present": bool(replica.official_pattern_label),
        "historical_priors_not_mandatory_nta": not service.historical_analytics().get(
            "mandatory_nta_quotas_invented", True
        ),
        "official_pattern_status_after_synthetic_link": status.value == "verified",
    }

    adversarial = _adversarial_matrix(session, ctx, service)

    verdict = "PASS" if all(checks.values()) and adversarial["all_pass"] else "FAIL"
    return {
        "day": 11,
        "candidate_sha": candidate_sha,
        "git_head_sha": head_sha,
        "verdict": verdict,
        "checks": checks,
        "adversarial": adversarial,
        "authority_before": authority_before,
        "authority_after": authority_after,
        "math_ten": math_ten.model_dump(),
        "algebra_ten": algebra_ten.model_dump(),
        "replica_summary": {
            "verdict": replica.verdict.value,
            "actual_count": replica.actual_count,
            "requested_count": replica.requested_count,
        },
        "governance": {
            "founder_approval": False,
            "official_nta_pdf_independent_review": "NOT_CLAIMED_SYNTHETIC_HARNESS_ONLY",
            "production_uat": "NOT_RUN",
        },
    }


def _adversarial_matrix(
    session: Session,
    ctx: dict[str, object],
    service: JeeMainExamIntelligenceService,
) -> dict[str, object]:
    from app.jee_main_exam_intelligence.contracts import PaperPlanRequest
    from app.jee_main_exam_intelligence.enums import JeeMainSubjectCode, PaperPlanIssueCode

    cases: dict[str, bool] = {}
    unknown_topic = PaperPlanRequest(
        plan_id="adv-unknown-topic",
        exam_version_code=JEE_MAIN_VERSION_2027,
        mode=PaperPlanMode.PRACTICE_EXACT_COUNT,
        organization_id=str(ctx["organization_id"]),
        subject_code=JeeMainSubjectCode.MATHEMATICS,
        topic_code="nonexistent-official-topic",
        requested_count=10,
    )
    cases["unknown_syllabus_topic_fails"] = (
        service.plan_paper(session, unknown_topic, persist=False).verdict == PaperPlanVerdict.FAIL
    )

    forged_group = build_practice_algebra_ten_request(ctx).model_copy(
        update={"derived_topic_group": "invented-nta-algebra-quota", "plan_id": "adv-forged-quota"}
    )
    cases["invented_derived_group_fails"] = (
        service.plan_paper(session, forged_group, persist=False).verdict == PaperPlanVerdict.FAIL
    )

    foreign = build_practice_math_ten_request(ctx).model_copy(
        update={"organization_id": "foreign-tenant", "plan_id": "adv-foreign"}
    )
    foreign_result = service.plan_paper(session, foreign, persist=False)
    cases["foreign_tenant_fail"] = (
        foreign_result.verdict == PaperPlanVerdict.FAIL
        or PaperPlanIssueCode.FOREIGN_TENANT_CONTENT in foreign_result.issue_codes
        or foreign_result.actual_count < 10
    )

    return {"cases": cases, "all_pass": all(cases.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description="Day 11 verification harness")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()
    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report = build_verification_report(session)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
