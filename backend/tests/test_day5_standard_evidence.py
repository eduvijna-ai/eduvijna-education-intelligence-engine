"""Standards cannot create typed competencies from registry-only or changed bytes."""

from __future__ import annotations

from typing import Any

import pytest

from app.curriculum_intelligence.framework_structure import (
    FrameworkStructureError,
    FrameworkStructureService,
)
from app.curriculum_intelligence.official_demo import official_source_demonstration
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.models.curriculum import EducationFramework
from app.schemas.curriculum_intelligence import CompetencySpec, OfficialSourceManifestEntry
from app.schemas.framework_structure import FrameworkNodeSpec
from tests.test_day4_official_evidence import (
    _official_test_revisions,
)  # noqa: F401
from tests.test_day4_official_evidence import (
    evidence_service as evidence_service,
)


def context(service: CurriculumIntelligenceService) -> tuple[Any, Any, FrameworkNodeSpec]:
    revisions = _official_test_revisions(service)
    report = official_source_demonstration(service, revisions)
    framework = service.session.get(EducationFramework, report["path"]["framework_id"])
    assert framework is not None
    raw = report["framework_structure"]["nodes"][-1]
    node_service = FrameworkStructureService(service.session, source_service=service.source_service)
    node = node_service.list_nodes(framework.id)[-1]
    # Find by level instead of sorting UUID identities.
    node = next(n for n in node_service.list_nodes(framework.id) if n.level == "competency")
    parent = next(n for n in node_service.list_nodes(framework.id) if n.id == node.parent_id)
    spec = FrameworkNodeSpec(
        level="competency",
        code=node.code,
        title=node.title,
        official_code=node.official_code,
        official_text=node.official_text,
        parent_code=parent.code,
        competency_id=node.competency_id,
        source_locator=node.source_locator,
        publication_status=node.publication_status,
        review_status=node.review_status,
        inferred=node.inferred,
    )
    assert raw
    return framework, revisions["ncert-grade-9-phase-i-part-2-draft"], spec


def test_registry_only_active_standard_cannot_attach_unscoped_competency(
    evidence_service: CurriculumIntelligenceService,
) -> None:
    framework, _, spec = context(evidence_service)
    revision = evidence_service.ensure_manifest_sources(
        [
            OfficialSourceManifestEntry(
                key="synthetic-standards-registry",
                source_type="official_authority",
                title="Synthetic registry standards",
                url="https://synthetic.example.invalid/standards",
                authority="Synthetic authority",
                document_type="academic_standards",
            )
        ],
        actor_id="test",
    )["synthetic-standards-registry"]
    assert revision.status == "active" and evidence_service.is_registry_only(revision)
    competency = evidence_service.upsert_competencies(
        framework=framework,
        revision=revision,
        specs=[CompetencySpec(code="unscoped-metadata-standard", name="Unverified standard")],
    )["unscoped-metadata-standard"]
    forged = spec.model_copy(update={"code": "metadata-only-node", "competency_id": competency.id})
    structure = FrameworkStructureService(
        evidence_service.session, source_service=evidence_service.source_service
    )
    before = len(structure.list_nodes(framework.id))
    with pytest.raises(FrameworkStructureError, match="original source content"):
        structure.upsert_nodes(framework=framework, revision=revision, specs=[forged])
    assert len(structure.list_nodes(framework.id)) == before


@pytest.mark.parametrize(
    "fault", ["bytes", "snapshot", "extracted", "locator", "wording", "missing-wording"]
)
def test_standards_bind_actual_bytes_and_exact_locator(
    evidence_service: CurriculumIntelligenceService,
    fault: str,
) -> None:
    framework, revision, spec = context(evidence_service)
    if fault == "bytes":
        evidence_service.source_service.storage._resolve_relative(
            revision.storage_path
        ).write_bytes(b"changed")
    elif fault == "snapshot":
        revision.metadata_json = {**revision.metadata_json, "source_snapshot": {}}
    elif fault == "extracted":
        revision.extracted_text += " tampered"
    elif fault == "locator":
        spec = spec.model_copy(update={"source_locator": "PDF page 1"})
    elif fault == "wording":
        spec = spec.model_copy(update={"official_code": "NOT-IN-SOURCE"})
    else:
        spec = spec.model_copy(update={"official_code": None, "official_text": None})
    evidence_service.session.flush()
    structure = FrameworkStructureService(
        evidence_service.session, source_service=evidence_service.source_service
    )
    with pytest.raises(FrameworkStructureError):
        structure.upsert_nodes(framework=framework, revision=revision, specs=[spec])
