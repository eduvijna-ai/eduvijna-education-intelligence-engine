"""Day 12 verification harness (D12-35 initial gates)."""

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
from app.jee_advanced.authority import resolve_profile_authority
from app.jee_advanced.constants import (
    EDUVIJNA_DERIVED_TOPIC_GROUP,
    JEE_ADVANCED_PACK_CODE,
    MATHEMATICS_SUBJECT,
)
from app.jee_advanced.contracts import (
    AdvancedPaperPlanRequest,
    SubjectPracticeRequest,
    TopicPracticeRequest,
)
from app.jee_advanced.enums import (
    AdvancedPlanVerdict,
    AdvancedProfileKind,
    JeeAdvancedSourceTrustMode,
)
from app.jee_advanced.exam_profile import ensure_exam_version, ensure_jee_advanced_exam_pack
from app.jee_advanced.governance import build_day12_governance_record
from app.jee_advanced.planner import JeeAdvancedPaperPlanner
from app.jee_advanced.practice_service import JeeAdvancedPracticeService
from app.jee_advanced.source_registry import (
    build_source_registry_snapshot,
    reference_evidence_ready,
)


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

    practice = JeeAdvancedPracticeService()
    math10 = practice.allocate_subject(
        SubjectPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            requested_count=10,
        )
    )
    algebra10 = practice.allocate_topic(
        TopicPracticeRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            subject_code=MATHEMATICS_SUBJECT,
            topic_group=EDUVIJNA_DERIVED_TOPIC_GROUP,
            requested_count=10,
        )
    )

    pack = ensure_jee_advanced_exam_pack(session)
    synthetic_version = ensure_exam_version(
        session,
        pack=pack,
        profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
        academic_year="2026",
    )
    session.commit()

    planner = JeeAdvancedPaperPlanner()
    pair_plan = planner.plan(
        AdvancedPaperPlanRequest(
            exam_pack_code=JEE_ADVANCED_PACK_CODE,
            profile_kind=AdvancedProfileKind.SYNTHETIC_DEMO,
            trust_mode=JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE,
            academic_year="2026",
            simulate_full_pair=True,
        )
    )
    official_2027 = resolve_profile_authority(
        profile_kind=AdvancedProfileKind.CANDIDATE_2027,
        academic_year="2027",
        reference_sources_approved=False,
    )

    return {
        "candidate_sha": candidate_sha,
        "head_sha": head_sha,
        "sha_alignment": candidate_sha == head_sha,
        "governance": build_day12_governance_record(),
        "source_registry": build_source_registry_snapshot(),
        "synthetic_fixture_pass": (
            math10.verdict.value == "pass"
            and math10.delivered_count == 10
            and algebra10.verdict.value == "pass"
            and algebra10.delivered_count == 10
        ),
        "reference_2026_curator_approved": reference_evidence_ready(),
        "official_2027_approved": False,
        "official_2027_gate": {
            "verdict": official_2027.verdict.value if official_2027.verdict else None,
            "trust_mode": official_2027.trust_mode.value,
        },
        "two_paper_profile": {
            "exam_pack_code": pack.code,
            "synthetic_version_code": synthetic_version.version_code,
            "section_count": len(synthetic_version.sections),
        },
        "synthetic_pair_plan_verdict": pair_plan.verdict.value,
        "trust_separation": {
            "synthetic": JeeAdvancedSourceTrustMode.SYNTHETIC_FIXTURE.value,
            "reference_2026": JeeAdvancedSourceTrustMode.HISTORICAL_REFERENCE_2026.value,
            "official_2027": JeeAdvancedSourceTrustMode.OFFICIAL_2027_NOT_VERIFIED.value,
        },
        "math10": math10.model_dump(),
        "algebra10": algebra10.model_dump(),
        "notes": {
            "compose_smoke": "NOT_RUN",
            "live_postgresql": "NOT_RUN",
            "anythingllm_live": "NOT_RUN",
            "reference_replica_without_curator": AdvancedPlanVerdict.REFERENCE_NOT_VERIFIED.value,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Day 12 verification harness")
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
        print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
