from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.education_intelligence.taxonomy_registry import TaxonomyRegistry
from app.models.curriculum import ConceptPrerequisite
from app.paper_distribution.contracts import (
    DistributionTarget,
    PaperDistributionRequest,
    PaperItemInput,
)
from app.paper_distribution.enums import PaperDistributionIssueCode, PaperDistributionVerdict
from app.paper_distribution.evaluator import evaluate_paper_distribution
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.enums import EdgeProvenanceClass
from app.prerequisite_intelligence.fixtures import (
    load_day10_fixture_snapshot,
    seed_day10_prerequisite_fixture,
)


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-adv.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_official_edge_without_allowlist_fails_audit(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    edge = session.scalars(
        select(ConceptPrerequisite).where(
            ConceptPrerequisite.prerequisite_concept_id == ctx["counting_concept_id"],
            ConceptPrerequisite.target_concept_id == ctx["whole_add_concept_id"],
        )
    ).first()
    assert edge is not None
    edge.metadata_json = {
        "provenance_class": EdgeProvenanceClass.OFFICIAL.value,
        "source_revision_id": ctx["source_revision_id"],
        "source_locator": "forged",
    }
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    assert all(edge.provenance_class != EdgeProvenanceClass.OFFICIAL for edge in snapshot.edges)
    report = build_graph_quality_report(snapshot, allowed_source_revision_ids=set())
    loader_issues = int(snapshot.metadata_json.get("loader_issue_count", 0))
    assert report.status.value != "pass" or loader_issues > 0


def test_duplicate_items_and_impossible_targets() -> None:
    items = [
        PaperItemInput(
            item_id="dup",
            cognitive_level="remember",
            competency_codes=["knowledge"],
            day6_validated=True,
        ),
        PaperItemInput(
            item_id="dup",
            cognitive_level="understand",
            competency_codes=["knowledge"],
            day6_validated=True,
        ),
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


def test_unvalidated_items_fail_closed() -> None:
    request = PaperDistributionRequest(
        paper_id="unvalidated",
        items=[
            PaperItemInput(
                item_id="q1",
                cognitive_level="remember",
                competency_codes=["knowledge"],
                day6_validated=False,
            )
        ],
    )
    result = evaluate_paper_distribution(request, taxonomy=TaxonomyRegistry())
    assert result.verdict != PaperDistributionVerdict.PASS
