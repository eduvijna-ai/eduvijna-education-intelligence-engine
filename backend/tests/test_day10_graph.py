from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.prerequisite_intelligence.enums import GraphAuditStatus, GraphIssueCode
from app.prerequisite_intelligence.fixtures import load_day10_fixture_snapshot, seed_day10_prerequisite_fixture
from app.prerequisite_intelligence.traversal import bounded_ancestor_paths


def _session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'd10-graph.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_fixture_graph_passes_audit_and_has_alternate_paths(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    report = build_graph_quality_report(
        snapshot, allowed_source_revision_ids={ctx["source_revision_id"]}
    )
    assert report.status == GraphAuditStatus.PASS
    paths, _ = bounded_ancestor_paths(snapshot, ctx["multi_add_concept_id"])
    assert len(paths) >= 2
    path_signatures = {tuple(p.concept_ids) for p in paths}
    assert len(path_signatures) >= 2


def test_cycle_detection_flags_error(tmp_path: Path) -> None:
    from app.models.curriculum import ConceptPrerequisite

    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.add(
        ConceptPrerequisite(
            prerequisite_concept_id=ctx["multi_add_concept_id"],
            target_concept_id=ctx["counting_concept_id"],
            metadata_json={"provenance_class": "synthetic"},
        )
    )
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    report = build_graph_quality_report(snapshot)
    codes = {issue.code for issue in report.issues}
    assert GraphIssueCode.CYCLE_DETECTED in codes
