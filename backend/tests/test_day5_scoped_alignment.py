"""Direct assertions require both original endpoints and exact shared scope."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_day5_scoped_curriculum import concept, scoped
from test_day5_scoped_curriculum import service as scoped_service_fixture

from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.models.curriculum import Competency, LearningOutcome
from app.models.curriculum_intelligence import CurriculumAlignment
from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import (
    CompetencySpec,
    CurriculumAlignmentInput,
    LearningOutcomeSpec,
)
from app.schemas.source_intelligence import SourceRegistrationInput

service = scoped_service_fixture

DIMENSIONS = {
    "grade": "grades",
    "medium": "media",
    "subject": "subjects",
    "course_family": "course_families",
    "course_group": "course_groups",
    "subject_language": "subject_languages",
    "language_role": "language_roles",
    "book_part": "book_parts",
    "bilingual": "bilingual_states",
}


def revision_for(
    service: CurriculumIntelligenceService,
    pack: str,
    *,
    domain: str,
    text: str,
    identities: list[dict[str, str]],
    declarations: list[dict[str, str]] | None = None,
) -> SourceRevision:
    scope: dict[str, Any] = {
        "pack_code": pack,
        "version_codes": ["synthetic-2025-26"],
        "publication_status": "draft",
        "applicability_status": "unverified",
    }
    for key, plural in DIMENSIONS.items():
        scope[plural] = sorted(
            {
                identity[key]
                for identity in identities
                if key in identity and identity[key] not in ("", "unknown")
            }
        )
    source = service.source_service.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_SYLLABUS
            if domain == "syllabus"
            else SourceType.OFFICIAL_AUTHORITY,
            title="Synthetic alignment evidence",
            url=f"https://synthetic.example.invalid/alignment/{uuid4()}.json",
            authority="Synthetic test authority",
            country="India",
            board_or_exam=pack,
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            copyright_classification="synthetic_fixture",
            metadata_json={
                "synthetic": True,
                "document_type": domain,
                "curriculum_scope": scope,
                "direct_alignments": declarations or [],
            },
        ),
        actor_id="test",
    )
    result = service.source_service.ingest_upload(
        source.id,
        method=SourceIngestionMethod.JSON,
        filename="alignment.json",
        content=json.dumps({"text": text}, ensure_ascii=False).encode(),
        actor_id="test",
    )
    service.source_service.extract_revision(result.id, actor_id="test")
    service.source_service.create_diff(result.id, actor_id="test")
    assert service.source_service.validate_revision(result.id, actor_id="test").valid
    service.source_service.approve_revision(result.id, actor_id="test")
    return service.source_service.activate_revision(result.id, actor_id="test")


def prepare(
    service: CurriculumIntelligenceService,
    *,
    kind: str,
    quote: str = "node-code",
    changed_dimension: str | None = None,
    incomplete_dimension: str | None = None,
    mapping_covers_target: bool = True,
) -> CurriculumAlignmentInput:
    version, _ = scoped(service)
    node = concept(service, version, "first-year-english-concept")
    node_identity = dict(node.metadata_json["identity"])
    target_identity = dict(node_identity)
    if changed_dimension:
        target_identity[changed_dimension] = "different-context"
    if incomplete_dimension:
        target_identity.pop(incomplete_dimension)
    target_words = "Explains the original scientific relationship"
    target_code = "OUT-1" if kind == "outcome" else "STD-1"
    target_revision = revision_for(
        service,
        version.curriculum_pack.code,
        domain="learning_outcomes" if kind == "outcome" else "academic_standard",
        text=f"{target_code}: {target_words}",
        identities=[node_identity, target_identity],
    )
    metadata = {"identity": target_identity, "official_code": target_code}
    target: LearningOutcome | Competency
    if kind == "outcome":
        target = service.upsert_learning_outcomes(
            version=version,
            revision=target_revision,
            specs=[
                LearningOutcomeSpec(
                    code="normalized-target",
                    text=target_words,
                    source_locator="JSON pointer /text",
                    metadata_json=metadata,
                )
            ],
        )["normalized-target"]
    else:
        target = service.upsert_competencies(
            framework=None,
            curriculum_version=version,
            revision=target_revision,
            specs=[
                CompetencySpec(
                    code="normalized-target",
                    name="Normalized display label",
                    official_text=target_words,
                    source_locator="JSON pointer /text",
                    metadata_json=metadata,
                )
            ],
        )["normalized-target"]
    quotes = {
        "node-code": f"{node.code} addresses {target_code}.",
        "original-words": f"{node.official_text} addresses {target_words}.",
        "unrelated": "Unrelated administrative publication notice.",
        "node-only": f"{node.code} describes a concept.",
        "target-only": f"{target_code} is published here.",
        "node-prefix": f"{node.code}-extended addresses {target_code}.",
        "target-prefix": f"{node.code} addresses {target_code}0.",
        "normalized-target": f"{node.code} addresses normalized-target.",
        "normalized-title": f"Invented display title addresses {target_code}.",
    }
    if quote == "normalized-title":
        node.title = "Invented display title"
    words = quotes[quote]
    declaration = {
        "node_code": node.code,
        "target_id": target.id,
        "relationship_type": "addresses",
        "source_locator": "JSON pointer /text",
        "evidence_text": words,
    }
    mapping = revision_for(
        service,
        version.curriculum_pack.code,
        domain="syllabus",
        text=words,
        identities=[node_identity, target_identity] if mapping_covers_target else [node_identity],
        declarations=[declaration],
    )
    return CurriculumAlignmentInput.model_validate(
        {
            "curriculum_version_id": version.id,
            "curriculum_node_id": node.id,
            "learning_outcome_id" if kind == "outcome" else "competency_id": target.id,
            "source_revision_id": mapping.id,
            "status": "direct",
            "relationship_type": "addresses",
            "source_locator": "JSON pointer /text",
            "evidence_text": words,
        }
    )


@pytest.mark.parametrize("kind", ["outcome", "competency"])
@pytest.mark.parametrize("quote", ["node-code", "original-words"])
def test_direct_alignment_accepts_two_original_endpoints(
    service: CurriculumIntelligenceService, kind: str, quote: str
) -> None:
    payload = prepare(service, kind=kind, quote=quote)
    result = service.align(payload)
    assert result.status == "direct"
    assert service.align(payload).id == result.id
    service.session.commit()
    service.session.expire_all()
    persisted = service.session.get(CurriculumAlignment, result.id)
    assert persisted is not None and persisted.evidence_text == payload.evidence_text


@pytest.mark.parametrize("kind", ["outcome", "competency"])
@pytest.mark.parametrize(
    "quote",
    [
        "unrelated",
        "node-only",
        "target-only",
        "node-prefix",
        "target-prefix",
        "normalized-target",
        "normalized-title",
    ],
)
def test_direct_alignment_rejects_unproven_endpoint_quote(
    service: CurriculumIntelligenceService, kind: str, quote: str
) -> None:
    payload = prepare(service, kind=kind, quote=quote)
    before = set(service.session.scalars(select(CurriculumAlignment.id)))
    with pytest.raises(ValueError, match="endpoint|mention"):
        service.align(payload)
    assert set(service.session.scalars(select(CurriculumAlignment.id))) == before


@pytest.mark.parametrize("kind", ["outcome", "competency"])
@pytest.mark.parametrize("dimension", list(DIMENSIONS))
def test_direct_alignment_rejects_cross_scope_target_even_if_mapping_covers_both(
    service: CurriculumIntelligenceService, kind: str, dimension: str
) -> None:
    payload = prepare(service, kind=kind, changed_dimension=dimension)
    with pytest.raises(ValueError, match="crosses endpoint"):
        service.align(payload)


@pytest.mark.parametrize("kind", ["outcome", "competency"])
@pytest.mark.parametrize("dimension", list(DIMENSIONS)[3:])
def test_direct_alignment_requires_complete_target_identity(
    service: CurriculumIntelligenceService, kind: str, dimension: str
) -> None:
    payload = prepare(service, kind=kind, incomplete_dimension=dimension)
    with pytest.raises(ValueError, match="complete endpoint"):
        service.align(payload)


@pytest.mark.parametrize("kind", ["outcome", "competency"])
def test_mapping_revision_must_cover_target_scope(
    service: CurriculumIntelligenceService, kind: str
) -> None:
    payload = prepare(service, kind=kind, changed_dimension="medium", mapping_covers_target=False)
    with pytest.raises(ValueError, match="medium scope"):
        service.align(payload)
