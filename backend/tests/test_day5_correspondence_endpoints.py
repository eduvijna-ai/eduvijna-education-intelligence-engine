"""Independent correspondence proofs using original synthetic source lifecycles."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.curriculum_intelligence.scoped_curriculum import link_correspondence
from app.curriculum_intelligence.service import CurriculumIntelligenceService
from app.models.curriculum import CurriculumNode, CurriculumVersion
from app.models.enums import SourceIngestionMethod, SourceTrustTier, SourceType
from app.models.source import SourceRevision
from app.schemas.curriculum_intelligence import CurriculumNodeSpec
from app.schemas.source_intelligence import SourceRegistrationInput
from tests.test_day5_scoped_curriculum import service as service  # noqa: F401


def source(
    service: CurriculumIntelligenceService,
    content: dict[str, str],
    declarations: list[dict[str, str]] | None = None,
) -> SourceRevision:
    registered = service.source_service.register_source(
        SourceRegistrationInput(
            source_type=SourceType.OFFICIAL_SYLLABUS,
            title="SYNTHETIC correspondence endpoint proof",
            url=f"https://example.invalid/{uuid4()}.json",
            authority="Synthetic authority",
            country="India",
            board_or_exam="endpoint-proof",
            academic_year="2025-26",
            copyright_classification="synthetic_fixture",
            trust_tier=SourceTrustTier.OFFICIAL_PRIMARY,
            metadata_json={
                "synthetic": True,
                "document_type": "syllabus",
                "correspondences": declarations or [],
                "curriculum_scope": {
                    "pack_code": "endpoint-proof",
                    "version_codes": ["test-version"],
                    "grades": ["VIII", "IX"],
                    "media": ["English", "Telugu"],
                    "subjects": ["science", "mathematics"],
                    "course_families": ["General", "Vocational"],
                    "course_groups": ["MPC", "BPC"],
                    "subject_languages": ["not_applicable", "English", "Telugu"],
                    "language_roles": ["first", "second"],
                    "book_parts": ["Part 1", "Part 2"],
                    "bilingual_states": ["no", "yes"],
                    "publication_status": "draft",
                    "applicability_status": "unverified",
                },
            },
        ),
        actor_id="test",
    )
    revision = service.source_service.ingest_upload(
        registered.id,
        method=SourceIngestionMethod.JSON,
        filename="endpoints.json",
        content=json.dumps(content, ensure_ascii=False).encode(),
        actor_id="test",
    )
    service.source_service.extract_revision(revision.id, actor_id="test")
    service.source_service.create_diff(revision.id, actor_id="test")
    assert service.source_service.validate_revision(revision.id, actor_id="test").valid
    service.source_service.approve_revision(revision.id, actor_id="test")
    return service.source_service.activate_revision(revision.id, actor_id="test")


def endpoints(
    service: CurriculumIntelligenceService,
    left_wording: str = "Left original science concept",
    right_wording: str = "తెలుగు మూల భావన",
    right_context: dict[str, str] | None = None,
    left_context: dict[str, str] | None = None,
    official_codes: bool = True,
) -> tuple[CurriculumVersion, CurriculumNode, CurriculumNode]:
    revision = source(
        service,
        {
            "left": f"OFF-L-1 {left_wording}" if official_codes else left_wording,
            "right": f"OFF-R-1 {right_wording}" if official_codes else right_wording,
        },
    )
    pack = service.ensure_pack(
        framework=None,
        code="endpoint-proof",
        name="Endpoint proof",
        authority="Synthetic authority",
        country="India",
        revision=revision,
        source_locator="JSON pointer /left",
    )
    version = service.ensure_version(
        pack=pack,
        version_code="test-version",
        academic_year="2025-26",
        revision=revision,
        active=False,
        source_locator="JSON pointer /left",
        metadata_json={"scope_enforced": True},
    )
    result = []
    for side, medium, wording, code in (
        ("left", "English", left_wording, "L-1"),
        ("right", "Telugu", right_wording, "R-1"),
    ):
        identity = {
            "grade": "VIII",
            "medium": medium,
            "subject": "science",
            "course_family": "General",
            "course_group": "MPC",
            "subject_language": "not_applicable",
            "language_role": "first",
            "book_part": "Part 1",
            "bilingual": "no",
        }
        identity.update((right_context if side == "right" else left_context) or {})
        specs = []
        parent = None
        for kind in ("grade_year", "medium", "subject", "unit", "chapter", "topic", "concept"):
            node_code = code if kind == "concept" else f"{side}-{kind}"
            specs.append(
                CurriculumNodeSpec(
                    node_type=kind,
                    code=node_code,
                    title=f"{side} {kind}",
                    parent_code=parent,
                    official_text=wording if kind == "concept" else None,
                    source_locator=f"JSON pointer /{side}",
                    metadata_json={
                        "identity": dict(identity),
                        **(
                            {"official_code": "OFF-L-1" if side == "left" else "OFF-R-1"}
                            if kind == "concept" and official_codes
                            else {}
                        ),
                    },
                )
            )
            parent = node_code
        result.append(service.upsert_nodes(version=version, revision=revision, specs=specs)[code])
    return version, result[0], result[1]


def link(
    service: CurriculumIntelligenceService,
    version: CurriculumVersion,
    left: CurriculumNode,
    right: CurriculumNode,
    evidence: str,
) -> str:
    declaration = {
        "left_code": left.code,
        "right_code": right.code,
        "locator": "JSON pointer /link",
        "evidence_text": evidence,
    }
    revision = source(service, {"link": evidence}, [declaration])
    return link_correspondence(
        service,
        version,
        left_node_id=left.id,
        right_node_id=right.id,
        revision=revision,
        locator=declaration["locator"],
        evidence_text=evidence,
    )


@pytest.mark.parametrize("mode", ["codes", "wording"])
def test_correspondence_identifies_both_endpoints_by_codes_or_original_wording(
    service: CurriculumIntelligenceService,
    mode: str,
) -> None:
    version, left, right = endpoints(service)
    evidence = (
        f"{left.metadata_json['official_code']} corresponds to "
        f"{right.metadata_json['official_code']}"
        if mode == "codes"
        else (f"{left.official_text} corresponds to {right.official_text}")
    )
    key = link(service, version, left, right, evidence)
    service.session.commit()
    service.session.expire_all()
    stored = version.metadata_json["cross_medium_correspondences"][key]
    assert stored["left_id"] == left.id and stored["right_id"] == right.id


@pytest.mark.parametrize(
    "evidence",
    [
        "Unrelated officially published sentence",
        "OFF-L-1 is a science concept",
        "OFF-R-1 is a science concept",
        "OFF-L-10 corresponds to OFF-R-10",
        "Left original science concept has a corresponding unnamed chapter",
    ],
)
def test_unrelated_one_sided_or_code_prefix_quotes_cannot_prove_relationship(
    service: CurriculumIntelligenceService,
    evidence: str,
) -> None:
    version, left, right = endpoints(service)
    before = dict(version.metadata_json)
    with pytest.raises(ValueError, match="both endpoints"):
        link(service, version, left, right, evidence)
    assert version.metadata_json == before


@pytest.mark.parametrize(
    "left_text,right_text,evidence",
    [
        ("force", "net force", "net force"),
        (
            "Shared original wording",
            "Shared original wording",
            "Shared original wording corresponds to Shared original wording",
        ),
    ],
)
def test_overlapping_or_identical_wording_does_not_identify_distinct_endpoints(
    service: CurriculumIntelligenceService,
    left_text: str,
    right_text: str,
    evidence: str,
) -> None:
    version, left, right = endpoints(service, left_text, right_text)
    with pytest.raises(ValueError, match="both endpoints"):
        link(service, version, left, right, evidence)
    assert "cross_medium_correspondences" not in version.metadata_json


@pytest.mark.parametrize(
    "dimension,value",
    [
        ("grade", "IX"),
        ("subject", "mathematics"),
        ("bilingual", "yes"),
        ("course_family", "Vocational"),
        ("course_group", "BPC"),
        ("language_role", "second"),
        ("book_part", "Part 2"),
    ],
)
def test_correspondence_rejects_endpoint_cross_context_even_when_both_globally_allowed(
    service: CurriculumIntelligenceService,
    dimension: str,
    value: str,
) -> None:
    version, left, right = endpoints(service, right_context={dimension: value})
    before = dict(version.metadata_json)
    with pytest.raises(ValueError, match="academic context"):
        link(service, version, left, right, "OFF-L-1 corresponds to OFF-R-1")
    assert version.metadata_json == before


def test_explicit_correspondence_allows_source_approved_subject_language_change(
    service: CurriculumIntelligenceService,
) -> None:
    version, left, right = endpoints(
        service,
        left_context={"subject_language": "English"},
        right_context={"subject_language": "Telugu"},
    )
    key = link(service, version, left, right, "OFF-L-1 corresponds to OFF-R-1")
    assert version.metadata_json["cross_medium_correspondences"][key]["right_id"] == right.id


@pytest.mark.parametrize("official_codes", [False, True])
def test_internal_node_codes_never_identify_source_endpoints(
    service: CurriculumIntelligenceService,
    official_codes: bool,
) -> None:
    version, left, right = endpoints(service, official_codes=official_codes)
    with pytest.raises(ValueError, match="both endpoints"):
        link(service, version, left, right, "L-1 corresponds to R-1")
    assert "cross_medium_correspondences" not in version.metadata_json


@pytest.mark.parametrize("only_code", ["OFF-L-1", "OFF-R-1"])
def test_shared_wording_plus_only_one_unique_official_code_cannot_prove_two_endpoints(
    service: CurriculumIntelligenceService,
    only_code: str,
) -> None:
    version, left, right = endpoints(service, "Shared original wording", "Shared original wording")
    with pytest.raises(ValueError, match="both endpoints"):
        link(service, version, left, right, f"{only_code} corresponds to Shared original wording")
    assert "cross_medium_correspondences" not in version.metadata_json


def test_both_own_source_official_codes_identify_endpoints_with_shared_wording(
    service: CurriculumIntelligenceService,
) -> None:
    version, left, right = endpoints(service, "Shared original wording", "Shared original wording")
    key = link(
        service, version, left, right, "OFF-L-1 corresponds to OFF-R-1: Shared original wording"
    )
    assert version.metadata_json["cross_medium_correspondences"][key]["right_id"] == right.id
