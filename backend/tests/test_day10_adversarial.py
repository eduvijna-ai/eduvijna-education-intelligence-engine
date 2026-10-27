from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.paper_distribution.contracts import DistributionTarget, PaperDistributionRequest, PaperItemInput
from app.paper_distribution.enums import PaperDistributionIssueCode
from app.paper_distribution.evaluator import evaluate_paper_distribution
from app.education_intelligence.taxonomy_registry import TaxonomyRegistry
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.enums import GraphIssueCode
from app.prerequisite_intelligence.fixtures import load_day10_fixture_snapshot, seed_day10_prerequisite_fixture


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-adv.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_unauthorized_official_provenance_review(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    report = build_graph_quality_report(snapshot, allowed_source_revision_ids={"foreign-revision"})
    codes = {issue.code for issue in report.issues}
    assert GraphIssueCode.UNAUTHORIZED_PROVENANCE in codes


def test_duplicate_items_and_impossible_targets() -> None:
    items = [
        PaperItemInput(item_id="dup", cognitive_level="remember", competency_codes=["knowledge"]),
        PaperItemInput(item_id="dup", cognitive_level="understand", competency_codes=["knowledge"]),
    ]
    request = PaperDistributionRequest(
        paper_id="adv",
        items=items,
        cognitive_targets=[
            DistributionTarget(dimension="cognitive", key="remember", exact_percent=60.0),
            DistributionTarget(dimension="cognitive", key="understand", exact_percent=60.0),
        ],
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert PaperDistributionIssueCode.DUPLICATE_ITEM_ID in result.issue_codes
    assert PaperDistributionIssueCode.TARGET_INFEASIBLE in result.issue_codes
