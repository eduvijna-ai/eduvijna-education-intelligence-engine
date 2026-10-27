from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.curriculum import (
    ConceptPrerequisite,
    CurriculumNode,
    CurriculumPack,
    CurriculumVersion,
    EducationFramework,
)
from app.models.enums import CurriculumNodeType, CurriculumStatus, SourceType
from app.models.source import Source, SourceRevision
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope, PrerequisiteGraphSnapshot
from app.prerequisite_intelligence.enums import EdgeProvenanceClass
from app.prerequisite_intelligence.loader import load_prerequisite_graph_snapshot


def seed_day10_prerequisite_fixture(session: Session) -> dict[str, str]:
    """Deterministic counting → addition → multi-step chain with alternate paths."""
    source = Source(
        source_type=SourceType.OFFICIAL_SYLLABUS.value,
        title="Day10 prerequisite fixture source (synthetic)",
    )
    framework = EducationFramework(code="d10-fw", name="D10 Framework", country="IN")
    pack = CurriculumPack(
        code="d10-pack",
        name="D10 Pack",
        country="IN",
        framework=framework,
    )
    version = CurriculumVersion(
        curriculum_pack=pack,
        version_code="d10-2026",
        status=CurriculumStatus.ACTIVE.value,
        metadata_json={"fixture": True},
    )
    subject = CurriculumNode(
        curriculum_version=version,
        node_type=CurriculumNodeType.SUBJECT.value,
        code="mathematics",
        title="Mathematics",
    )
    counting = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="counting-sequence",
        title="Counting sequence",
        metadata_json={"grade_year_code": "grade-2", "subject_code": "mathematics"},
    )
    whole_add = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="whole-number-addition",
        title="Whole-number addition",
        metadata_json={"grade_year_code": "grade-3", "subject_code": "mathematics"},
    )
    multi_add = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="multi-step-addition",
        title="Multi-step addition",
        metadata_json={"grade_year_code": "grade-4", "subject_code": "mathematics"},
    )
    place_value = CurriculumNode(
        curriculum_version=version,
        parent=subject,
        node_type=CurriculumNodeType.CONCEPT.value,
        code="place-value-tens",
        title="Place value (tens)",
        metadata_json={"grade_year_code": "grade-3", "subject_code": "mathematics"},
    )
    session.add_all(
        [source, framework, pack, version, subject, counting, whole_add, multi_add, place_value]
    )
    session.flush()
    revision = SourceRevision(
        source_id=source.id,
        revision_number=1,
        checksum="e" * 64,
        source_snapshot_checksum="f" * 64,
        ingestion_method="manual",
        content_type="text/plain",
        byte_size=1,
        retrieved_at=datetime.now(UTC),
        status="active",
        active_slot=1,
        extraction_status="succeeded",
        extracted_checksum="e" * 64,
        metadata_json={"fixture": True, "synthetic": True},
    )
    session.add(revision)
    session.flush()

    def official_edge(prereq: CurriculumNode, target: CurriculumNode) -> ConceptPrerequisite:
        return ConceptPrerequisite(
            prerequisite_concept=prereq,
            target_concept=target,
            weight=0.9,
            metadata_json={
                "provenance_class": EdgeProvenanceClass.OFFICIAL.value,
                "source_revision_id": revision.id,
                "source_locator": f"{prereq.code}->{target.code}",
            },
        )

    session.add_all(
        [
            official_edge(counting, whole_add),
            official_edge(whole_add, multi_add),
            official_edge(place_value, multi_add),
            official_edge(counting, place_value),
        ]
    )
    session.flush()
    return {
        "curriculum_version_id": version.id,
        "source_revision_id": revision.id,
        "counting_concept_id": counting.id,
        "whole_add_concept_id": whole_add.id,
        "multi_add_concept_id": multi_add.id,
        "place_value_concept_id": place_value.id,
        "organization_id": "d10-org-fixture",
        "institution_id": "d10-inst-fixture",
    }


def load_day10_fixture_snapshot(
    session: Session, ctx: dict[str, str]
) -> PrerequisiteGraphSnapshot:
    scope = PrerequisiteGraphScope(
        curriculum_version_id=ctx["curriculum_version_id"],
        grade_year_code=None,
        subject_code="mathematics",
        organization_id=ctx.get("organization_id"),
        institution_id=ctx.get("institution_id"),
    )
    return load_prerequisite_graph_snapshot(session, scope)
