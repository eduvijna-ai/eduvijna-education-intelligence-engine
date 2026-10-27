from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models.curriculum import ConceptPrerequisite, CurriculumNode, CurriculumVersion
from app.models.enums import CurriculumNodeType
from app.prerequisite_intelligence.audit import build_graph_quality_report
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.prerequisite_intelligence.enums import (
    EdgeProvenanceClass,
    GraphAuditStatus,
    GraphIssueCode,
)
from app.prerequisite_intelligence.fixtures import (
    load_day10_fixture_snapshot,
    seed_day10_prerequisite_fixture,
)
from app.prerequisite_intelligence.loader import load_prerequisite_graph_snapshot
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
    report = build_graph_quality_report(snapshot)
    assert report.status == GraphAuditStatus.PASS
    assert all(edge.provenance_class == EdgeProvenanceClass.SYNTHETIC for edge in snapshot.edges)
    paths, _ = bounded_ancestor_paths(snapshot, ctx["multi_add_concept_id"])
    assert len(paths) >= 2
    path_signatures = {tuple(p.concept_ids) for p in paths}
    assert len(path_signatures) >= 2


def test_cycle_detection_flags_error(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.add(
        ConceptPrerequisite(
            prerequisite_concept_id=ctx["multi_add_concept_id"],
            target_concept_id=ctx["counting_concept_id"],
            metadata_json={"provenance_class": "synthetic", "synthetic_fixture": True},
        )
    )
    session.commit()
    snapshot = load_day10_fixture_snapshot(session, ctx)
    report = build_graph_quality_report(snapshot)
    codes = {issue.code for issue in report.issues}
    assert GraphIssueCode.CYCLE_DETECTED in codes


def test_medium_resolved_from_ancestor_not_concept_metadata(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    version = session.get(CurriculumVersion, ctx["curriculum_version_id"])
    assert version is not None
    grade = CurriculumNode(
        curriculum_version=version,
        node_type=CurriculumNodeType.GRADE_YEAR.value,
        code="grade-4",
        title="Grade 4",
    )
    medium_en = CurriculumNode(
        curriculum_version=version,
        parent=grade,
        node_type=CurriculumNodeType.MEDIUM.value,
        code="english",
        title="English medium",
    )
    subject = CurriculumNode(
        curriculum_version=version,
        parent=medium_en,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics-en",
        title="Mathematics EN",
    )
    concept = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="en-medium-concept",
        title="Concept without medium metadata",
        metadata_json={"subject_code": "mathematics-en"},
    )
    session.add_all([grade, medium_en, subject, concept])
    session.commit()
    scope = PrerequisiteGraphScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        medium_code="english",
        subject_code="mathematics-en",
    )
    snapshot = load_prerequisite_graph_snapshot(session, scope)
    codes = {node.concept_code for node in snapshot.nodes}
    assert "en-medium-concept" in codes


def test_forged_medium_metadata_excluded_under_english_scope(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    version = session.get(CurriculumVersion, ctx["curriculum_version_id"])
    assert version is not None
    grade = CurriculumNode(
        curriculum_version=version,
        node_type=CurriculumNodeType.GRADE_YEAR.value,
        code="grade-5",
        title="Grade 5",
    )
    medium_te = CurriculumNode(
        curriculum_version=version,
        parent=grade,
        node_type=CurriculumNodeType.MEDIUM.value,
        code="telugu",
        title="Telugu medium",
    )
    subject = CurriculumNode(
        curriculum_version=version,
        parent=medium_te,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics-te",
        title="Mathematics TE",
    )
    concept = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="forged-medium-concept",
        title="Forged medium metadata",
        metadata_json={"medium_code": "english", "subject_code": "mathematics-te"},
    )
    session.add_all([grade, medium_te, subject, concept])
    session.commit()
    scope = PrerequisiteGraphScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        medium_code="english",
        subject_code="mathematics-te",
    )
    snapshot = load_prerequisite_graph_snapshot(session, scope)
    codes = {node.concept_code for node in snapshot.nodes}
    assert "forged-medium-concept" not in codes


def test_grade_scope_keeps_cross_grade_prerequisite_nodes(tmp_path: Path) -> None:
    session = _session(tmp_path)
    ctx = seed_day10_prerequisite_fixture(session)
    session.commit()
    scope = PrerequisiteGraphScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        grade_year_code="grade-4",
        subject_code="mathematics",
        organization_id=ctx["organization_id"],
        institution_id=ctx["institution_id"],
    )
    snapshot = load_prerequisite_graph_snapshot(session, scope)
    codes = {node.concept_code for node in snapshot.nodes}
    assert "multi-step-addition" in codes
    assert "counting-sequence" in codes
    paths, _ = bounded_ancestor_paths(snapshot, ctx["multi_add_concept_id"])
    assert len(paths) >= 1
