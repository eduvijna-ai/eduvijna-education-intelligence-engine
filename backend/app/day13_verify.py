"""Day 13 verification harness (D13-35)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.cuet_clat.authority import resolve_clat_authority, resolve_cuet_authority
from app.cuet_clat.clat_passage_contracts import CLAT_PASSAGE_HARNESS_TOKEN
from app.cuet_clat.clat_planner import ClatPaperPlanner
from app.cuet_clat.clat_validated_passage_service import (
    build_validated_clat_original_passage_examples,
)
from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE, MATHEMATICS_DOMAIN
from app.cuet_clat.contracts import ClatPaperPlanRequest, CuetPracticeRequest, CuetSingleTestRequest
from app.cuet_clat.cuet_persisted_pool import seed_validated_cuet_math_questions
from app.cuet_clat.enums import CuetClatProfileKind, CuetClatSourceTrustMode, PlanVerdict
from app.cuet_clat.exam_profile import ensure_synthetic_demo_versions
from app.cuet_clat.governance import build_day13_governance_record
from app.cuet_clat.persisted_context import trusted_persisted_context
from app.cuet_clat.practice_service import CuetPracticeService
from app.cuet_clat.scope_ledger import load_repo_scope_counts
from app.cuet_clat.source_registry import build_source_registry_snapshot
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1]
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
    candidate_sha = _resolve_candidate_sha()
    head_sha = _git_head()
    sha_aligned = candidate_sha == head_sha and candidate_sha not in {"", "unknown"}

    practice = CuetPracticeService()
    math10 = practice.allocate_practice(
        CuetPracticeRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            test_subject_code=MATHEMATICS_DOMAIN,
            requested_count=10,
            academic_year="2026",
        )
    )
    single50 = practice.assemble_single_test(
        CuetSingleTestRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            test_subject_code=MATHEMATICS_DOMAIN,
            academic_year="2026",
        )
    )

    cuet_2027 = resolve_cuet_authority(
        profile_kind=CuetClatProfileKind.CUET_CANDIDATE_2027,
        academic_year="2027",
        session=session,
    )

    planner = ClatPaperPlanner()
    clat_plan = planner.plan(
        ClatPaperPlanRequest(
            exam_pack_code=CLAT_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2027",
        )
    )
    clat_official = resolve_clat_authority(
        profile_kind=CuetClatProfileKind.CLAT_2027,
        academic_year="2027",
        session=session,
    )

    clat_passage_examples = build_validated_clat_original_passage_examples(
        harness_authorized=True,
        trusted_harness_token=CLAT_PASSAGE_HARNESS_TOKEN,
    )

    cuet_ver, _ = ensure_synthetic_demo_versions(session)
    org_id = "d13-verify-org"
    inst_id = "d13-verify-inst"
    seeded = seed_validated_cuet_math_questions(
        session,
        organization_id=org_id,
        institution_id=inst_id,
        exam_version_id=str(cuet_ver.id),
        pool_size=50,
    )
    persisted_ctx = trusted_persisted_context(
        exam_version_id=str(cuet_ver.id),
        organization_id=org_id,
        institution_id=inst_id,
        academic_year="2026",
    )
    persisted_math10 = practice.allocate_practice(
        CuetPracticeRequest(
            exam_pack_code=CUET_PACK_CODE,
            profile_kind=CuetClatProfileKind.SYNTHETIC_DEMO,
            trust_mode=CuetClatSourceTrustMode.SYNTHETIC_FIXTURE,
            test_subject_code=MATHEMATICS_DOMAIN,
            requested_count=10,
            academic_year="2026",
            organization_id=org_id,
        ),
        session=session,
        persisted=persisted_ctx,
    )
    session.commit()

    scope_counts = load_repo_scope_counts()

    synthetic_ok = (
        math10.verdict == PlanVerdict.PASS
        and math10.delivered_count == 10
        and single50.verdict == PlanVerdict.PASS
        and single50.question_count == 50
        and clat_plan.verdict == PlanVerdict.PASS
        and clat_plan.total_questions == 120
        and len(clat_plan.passage_clusters) > 0
        and sha_aligned
        and scope_counts.get("TOTAL") == 36
    )

    return {
        "ok": synthetic_ok,
        "candidate_sha": candidate_sha,
        "head_sha": head_sha,
        "sha_alignment": sha_aligned,
        "governance": build_day13_governance_record(),
        "source_registry": build_source_registry_snapshot(session),
        "synthetic_fixture_pass": synthetic_ok,
        "validated_persisted_synthetic": {
            "pool_seeded_count": len(seeded),
            "math10_verdict": persisted_math10.verdict.value,
            "math10_delivered": persisted_math10.delivered_count,
            "independently_validated": bool(
                persisted_math10.metadata_json.get("validated_persisted_synthetic")
            ),
            "has_real_stems": all(
                bool(q.stem_text and q.options) for q in persisted_math10.questions
            ),
        },
        "cuet_reference_curator_approved": False,
        "clat_official_curator_approved": False,
        "cuet_2027_official_verified": False,
        "cuet_2027_gate": {
            "verdict": cuet_2027.verdict.value if cuet_2027.verdict else None,
            "trust_mode": cuet_2027.trust_mode.value,
        },
        "clat_official_gate": {
            "verdict": clat_official.verdict.value if clat_official.verdict else None,
            "trust_mode": clat_official.trust_mode.value,
        },
        "scope_ledger_counts": scope_counts,
        "math10": math10.model_dump(),
        "cuet_single_test_50": single50.model_dump(),
        "clat_plan_summary": {
            "total_questions": clat_plan.total_questions,
            "passage_cluster_count": len(clat_plan.passage_clusters),
            "section_allocations": [s.model_dump() for s in clat_plan.section_allocations],
            "verdict": clat_plan.verdict.value,
            "demonstration_only": clat_plan.metadata_json.get("demonstration_only"),
        },
        "validated_clat_original_passage_examples": {
            "verdict": clat_passage_examples.verdict.value,
            "item_count": clat_passage_examples.item_count,
            "passage_count": clat_passage_examples.passage_count,
            "official_source_verified": clat_passage_examples.official_source_verified,
            "independent_validated_count": clat_passage_examples.metadata_json.get(
                "validated_independent_count"
            ),
            "harness_only": True,
        },
        "trust_separation": {
            "synthetic": CuetClatSourceTrustMode.SYNTHETIC_FIXTURE.value,
            "cuet_2026_ref": CuetClatSourceTrustMode.CUET_HISTORICAL_2026.value,
            "cuet_2027": CuetClatSourceTrustMode.CUET_2027_NOT_VERIFIED.value,
            "clat_2027": CuetClatSourceTrustMode.CLAT_OFFICIAL_2027.value,
        },
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "anythingllm_live": "NOT_RUN",
            "full_historical_pytest": "NOT_RUN",
            "d13_36_founder_signoff": "NOT_STARTED",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 13 verification harness")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report = build_verification_report(session)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Day 13 verification:", "PASS" if report.get("ok") else "FAIL")
        print(json.dumps(report, indent=2, default=str))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())