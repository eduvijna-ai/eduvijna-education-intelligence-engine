"""Independent-review regressions: full applicability and source-purpose isolation."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.curriculum_intelligence.framework_structure import (
    FrameworkStructureError,
    FrameworkStructureService,
)
from app.curriculum_intelligence.scoped_curriculum import query_scoped_paths
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.curriculum_intelligence.source_domains import require_domain
from app.models.curriculum import CurriculumNode, EducationFramework
from app.models.source import SourceRevision
from app.schemas.framework_structure import FrameworkNodeSpec
from tests.test_day5_scoped_curriculum import concept, scoped  # noqa: F401
from tests.test_day5_scoped_curriculum import service as service
from tests.test_day5_source_domains import _change_domain  # noqa: F401
from tests.test_day5_source_domains import seeded as seeded


@pytest.mark.parametrize(
    "dimension",
    [
        "course_family",
        "course_group",
        "subject_language",
        "language_role",
        "book_part",
        "bilingual",
    ],
)
def test_lookup_cannot_publish_partial_applicability_as_universal(
    service: CurriculumIntelligenceService,
    dimension: str,
) -> None:
    version, _ = scoped(service)
    original = concept(service, version, "first-year-english-concept")
    original.metadata_json = {"identity": {**original.metadata_json["identity"], dimension: "A"}}
    other = CurriculumNode(
        id=str(uuid4()),
        curriculum_version_id=version.id,
        parent_id=original.parent_id,
        parent_version_id=version.id,
        node_type="concept",
        code="other-applicability",
        title="Synthetic other applicability",
        source_revision_id=original.source_revision_id,
        source_locator=original.source_locator,
        metadata_json={"identity": {**original.metadata_json["identity"], dimension: "B"}},
    )
    service.session.add(other)
    service.session.flush()
    args = dict(
        pack_code=version.curriculum_pack.code,
        version_code=version.version_code,
        grade="First Year",
        medium="English",
        subject="science",
    )
    missing = query_scoped_paths(service, **args)
    assert missing["status"] == "ambiguous" and missing["paths"] == []
    selected = query_scoped_paths(service, **args, **{dimension: "A"})
    assert selected["status"] == "matched"
    assert [p["node_ids"][-1] for p in selected["paths"]] == [original.id]
    assert query_scoped_paths(service, **args, **{dimension: "unknown"})["paths"] == []
    assert (
        query_scoped_paths(service, **args, **{dimension: "not_applicable"})["status"] == "no_match"
    )


@pytest.mark.parametrize("level", ["stage", "curricular_area", "goal"])
def test_standards_cannot_create_framework_ancestors(seeded, level: str) -> None:  # type: ignore[no-untyped-def]
    session, result = seeded
    framework = session.get(EducationFramework, result["framework"]["id"])
    assert framework is not None
    revision = session.get(SourceRevision, framework.source_revision_id)
    assert revision is not None
    _change_domain(session, revision, "academic_standards")
    with pytest.raises(FrameworkStructureError, match="only add competencies"):
        FrameworkStructureService(session).upsert_nodes(
            framework=framework,
            revision=revision,
            specs=[
                FrameworkNodeSpec(
                    level=level,
                    code="forbidden-root",
                    title="Unsupported",
                    source_locator="synthetic",
                    publication_status="draft",
                )
            ],
        )
    assert not session.new


@pytest.mark.parametrize(
    "purpose",
    ["membership", "framework", "framework_structure", "outcome", "competency", "alignment"],
)
def test_annual_plan_never_becomes_governing_semantics(purpose: str) -> None:
    with pytest.raises(ValueError, match="calendar"):
        require_domain(
            {
                "source_type": "official_authority",
                "metadata_json": {"document_type": "annual_plan"},
            },
            purpose,
        )


def test_same_physical_url_keeps_independent_semantic_source_identity(
    service: CurriculumIntelligenceService,
) -> None:
    from app.schemas.curriculum_intelligence import OfficialSourceManifestEntry

    entries = [
        OfficialSourceManifestEntry(
            key="synthetic-" + domain,
            source_type="official_authority",
            title="Synthetic " + domain,
            url="https://synthetic.example.invalid/handbook.pdf",
            authority="Synthetic authority",
            document_type=domain,
        )
        for domain in ("teacher_handbook", "academic_standards", "learning_outcomes")
    ]
    first = service.ensure_manifest_sources(entries, actor_id="synthetic-test")
    second = service.ensure_manifest_sources(entries, actor_id="synthetic-test")
    assert {key: rev.id for key, rev in first.items()} == {
        key: rev.id for key, rev in second.items()
    }
    assert len({rev.source_id for rev in first.values()}) == 3
    assert {service._source_metadata(rev)["document_type"] for rev in first.values()} == {
        "teacher_handbook",
        "academic_standards",
        "learning_outcomes",
    }
