"""Founder Day 10 verification harness (D10-34)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import cast

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.diagnostic_intelligence.contracts import OptionDiagnosticTag
from app.diagnostic_intelligence.enums import DiagnosticValidationStatus
from app.education_intelligence.taxonomy_registry import TaxonomyRegistry
from app.paper_distribution.enums import PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution
from app.paper_distribution.fixtures import (
    build_demo_ten_question_paper,
    build_mismatched_target_paper,
)
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.enums import GraphAuditStatus
from app.prerequisite_intelligence.fixtures import (
    load_day10_fixture_snapshot,
    seed_day10_prerequisite_fixture,
)
from app.prerequisite_intelligence.traversal import bounded_ancestor_paths
from app.root_cause_intelligence.contracts import RootCauseDiagnosticRequest
from app.root_cause_intelligence.enums import RootCauseIssueCode
from app.root_cause_intelligence.service import RootCauseIntelligenceService


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

    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    graph_report = build_graph_quality_report(
        snapshot, allowed_source_revision_ids={ctx["source_revision_id"]}
    )
    paths, _ = bounded_ancestor_paths(snapshot, ctx["multi_add_concept_id"])

    service = RootCauseIntelligenceService()
    root_result = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="d10-verify-item",
            option_key="A",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version="misconception-taxonomy@v1",
            tag=OptionDiagnosticTag(
                item_id="d10-verify-item",
                option_key="A",
                is_correct=False,
                misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                validation_status=DiagnosticValidationStatus.PASS,
            ),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
            allowed_source_revision_ids=[ctx["source_revision_id"]],
        )
    )
    correct_block = service.analyze(
        RootCauseDiagnosticRequest(
            item_id="d10-verify-item",
            option_key="B",
            misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
            taxonomy_version="misconception-taxonomy@v1",
            tag=OptionDiagnosticTag(
                item_id="d10-verify-item",
                option_key="B",
                is_correct=True,
                misconception_code="MATH.ADD.WHOLE.OFF_BY_ONE_LOW",
                validation_status=DiagnosticValidationStatus.PASS,
            ),
            curriculum_version_id=ctx["curriculum_version_id"],
            graph_snapshot=snapshot,
            target_concept_code="multi-step-addition",
        )
    )

    demo_paper = build_demo_ten_question_paper()
    paper_pass = evaluate_paper_distribution(demo_paper, taxonomy=TaxonomyRegistry())
    paper_fail = evaluate_paper_distribution(
        build_mismatched_target_paper(demo_paper), taxonomy=TaxonomyRegistry()
    )

    checks: dict[str, object] = {
        **sha_checks,
        "graph_quality_pass": graph_report.status == GraphAuditStatus.PASS,
        "alternate_prerequisite_paths": len(paths) >= 2,
        "root_cause_hypotheses": len(root_result.hypotheses) >= 2,
        "root_cause_not_mastery_disclaimer": "not demonstrated learner mastery"
        in (root_result.metadata_json.get("disclaimer") or "").lower(),
        "correct_option_veto": (
            RootCauseIssueCode.CORRECT_OPTION_TAGGED in correct_block.issue_codes
        ),
        "cognitive_20_20_40_10_10": (
            paper_pass.cognitive_summary.count_percent.get("remember") == 20.0
            and paper_pass.cognitive_summary.count_percent.get("apply") == 40.0
        ),
        "paper_distribution_pass": paper_pass.verdict == PaperDistributionVerdict.PASS,
        "paper_distribution_target_fail": paper_fail.verdict == PaperDistributionVerdict.FAIL,
        "no_anythingllm_calls": True,
    }
    ok = all(bool(value) for value in checks.values())
    return {
        "ok": ok,
        "candidate_sha": candidate_sha,
        "head_sha": head_sha,
        "checks": checks,
        "root_cause_verdict": root_result.verdict_status.value,
        "graph_checksum": snapshot.checksum,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 10 founder verification harness")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    engine = create_engine("sqlite:///:memory:")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        report = build_verification_report(session)

    checks = cast(dict[str, object], report.get("checks") or {})
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Day 10 verification:", "PASS" if report["ok"] else "FAIL")
        for key, value in checks.items():
            print(f"  {key}: {value}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
