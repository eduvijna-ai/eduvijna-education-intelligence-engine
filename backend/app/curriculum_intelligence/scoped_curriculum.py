"""Board-neutral exact-source scope checks for additional CurriculumPacks.

These guards extend the existing service, rather than creating a second engine.
Legacy unscoped versions remain readable. New scoped versions explicitly bind
all dimensions to reviewed immutable source metadata and original bytes.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.curriculum_intelligence.scoped_catalogue import checked_text, normalize_label
from app.curriculum_intelligence.source_domains import source_domain
from app.curriculum_intelligence.standards_evidence import (
    StandardsEvidenceError,
    require_endpoint_mentions,
    require_source_wording,
    source_text_at_locator,
)
from app.models.enums import SourceRevisionStatus

if TYPE_CHECKING:
    from app.curriculum_intelligence.service import CurriculumIntelligenceService
    from app.models.curriculum import CurriculumVersion
    from app.models.source import SourceRevision


class ScopeError(ValueError):
    pass


class SourceCurriculumScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    pack_code: str = Field(min_length=1)
    version_codes: tuple[str, ...] = Field(min_length=1)
    grades: tuple[str, ...] = ()
    media: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    course_families: tuple[str, ...] = ()
    course_groups: tuple[str, ...] = ()
    subject_languages: tuple[str, ...] = ()
    language_roles: tuple[str, ...] = ()
    book_parts: tuple[str, ...] = ()
    bilingual_states: tuple[str, ...] = ()
    publication_status: Literal["draft", "final", "unknown"] = "unknown"
    applicability_status: Literal["verified", "unverified"] = "unverified"
    applicability_locator: str | None = None

    @model_validator(mode="after")
    def check_scope(self) -> SourceCurriculumScope:
        for values in (
            self.version_codes,
            self.grades,
            self.media,
            self.subjects,
            self.course_families,
            self.course_groups,
            self.subject_languages,
            self.language_roles,
            self.book_parts,
            self.bilingual_states,
        ):
            keys = [normalize_label(value) for value in values]
            if len(keys) != len(set(keys)) or "unknown" in keys:
                raise ValueError("duplicate or unknown claimed source scope")
        if self.applicability_status == "verified" and not self.applicability_locator:
            raise ValueError("verified applicability requires exact source locator")
        checked_text(self.pack_code)
        return self


def exact_scope(
    service: CurriculumIntelligenceService, revision: SourceRevision
) -> SourceCurriculumScope:
    if revision.status != SourceRevisionStatus.ACTIVE.value:
        raise ScopeError("New scoped writes require active source evidence")
    if not service.has_source_content(revision) or not revision.storage_path:
        raise ScopeError("Scoped curriculum requires retrieved original source bytes")
    content = service.source_service.storage.read(revision.storage_path)
    if (
        len(content) != revision.byte_size
        or hashlib.sha256(content).hexdigest() != revision.checksum
    ):
        raise ScopeError("Exact source-byte integrity mismatch")
    snapshot = revision.metadata_json.get("source_snapshot", {})
    if service.source_service._snapshot_checksum(snapshot) != revision.source_snapshot_checksum:
        raise ScopeError("Immutable source metadata checksum mismatch")
    if (
        not revision.approval_fingerprint
        or revision.approval_fingerprint != service.source_service._approval_fingerprint(revision)
    ):
        raise ScopeError("Source evidence changed after approval")
    checked_text(revision.extracted_text or "")
    metadata = service._source_metadata(revision)
    if source_domain(snapshot) is None:
        raise ScopeError("Scoped evidence must declare a known document domain")
    if "curriculum_scope" not in metadata:
        raise ScopeError("Source curriculum scope is missing; review required")
    scope = SourceCurriculumScope.model_validate(metadata["curriculum_scope"])
    if scope.applicability_locator is not None:
        source_text_at_locator(
            service.source_service, revision, locator=scope.applicability_locator
        )
    return scope


def validate_version_scope(
    service: CurriculumIntelligenceService,
    revision: SourceRevision,
    *,
    pack_code: str,
    version_code: str,
    active: bool,
) -> SourceCurriculumScope:
    scope = exact_scope(service, revision)
    if scope.pack_code != pack_code or version_code not in scope.version_codes:
        raise ScopeError("Source evidence crosses curriculum pack or academic version")
    if active and (scope.publication_status != "final" or scope.applicability_status != "verified"):
        raise ScopeError("Draft or unverified source cannot activate a curriculum version")
    return scope


def validate_entity_scope(
    service: CurriculumIntelligenceService,
    version: CurriculumVersion,
    revision: SourceRevision,
    metadata: dict[str, Any],
    *,
    node_type: str | None = None,
    parent_metadata: dict[str, Any] | None = None,
) -> None:
    if not version.metadata_json.get("scope_enforced"):
        return
    if version.status == "superseded":
        raise ScopeError("Historical scoped curriculum versions are read-only")
    scope = validate_version_scope(
        service,
        revision,
        pack_code=version.curriculum_pack.code,
        version_code=version.version_code,
        active=False,
    )
    identity = metadata.get("identity")
    if not isinstance(identity, dict):
        raise ScopeError("Scoped curriculum entity requires explicit identity")
    required = ("grade", "medium", "subject")
    for key, allowed in (
        ("grade", scope.grades),
        ("medium", scope.media),
        ("subject", scope.subjects),
    ):
        value = identity.get(key)
        if key in required and (not value or value == "unknown" or value not in allowed):
            raise ScopeError(f"Source does not establish exact {key} scope")
        if value and value != "unknown" and value not in allowed:
            raise ScopeError(f"Source has incompatible {key} scope")
    for key, allowed in (
        ("course_family", scope.course_families),
        ("course_group", scope.course_groups),
        ("subject_language", scope.subject_languages),
        ("language_role", scope.language_roles),
        ("book_part", scope.book_parts),
        ("bilingual", scope.bilingual_states),
    ):
        value = identity.get(key)
        if node_type is not None and (not value or value == "unknown" or value not in allowed):
            raise ScopeError(f"Hierarchy node requires source-declared {key} applicability")
        if value not in (None, "unknown") and value not in allowed:
            raise ScopeError(f"Source does not establish exact {key} applicability")
    parent = (parent_metadata or {}).get("identity", {})
    for key in (
        "grade",
        "medium",
        "subject",
        "course_family",
        "course_group",
        "subject_language",
        "language_role",
        "book_part",
        "bilingual",
    ):
        if node_type is not None and parent_metadata is not None and key not in parent:
            raise ScopeError(f"Hierarchy parent requires source-declared {key} identity")
        if key in parent and identity.get(key) != parent[key]:
            raise ScopeError(f"Hierarchy crosses parent {key} scope")


def assert_immutable(entity: Any, values: dict[str, Any]) -> None:
    if any(getattr(entity, key) != value for key, value in values.items()):
        raise ScopeError("Source-backed scoped records are immutable; create reviewed new version")


def validate_correspondence_record(
    service: CurriculumIntelligenceService,
    version: CurriculumVersion,
    record: dict[str, Any],
) -> str:
    """Read-only proof of exact endpoints, own-source paths and relationship bytes."""
    import json

    from sqlalchemy import select

    from app.models.curriculum import CurriculumNode
    from app.models.source import SourceRevision

    fields = {
        "left_code",
        "right_code",
        "locator",
        "evidence_text",
        "left_id",
        "right_id",
        "source_revision_id",
        "source_checksum",
    }
    if set(record) != fields or any(
        not isinstance(record[field], str) or not record[field].strip() for field in fields
    ):
        raise ScopeError("Correspondence record requires complete exact evidence")
    if not version.metadata_json.get("scope_enforced"):
        raise ScopeError("Correspondence requires explicit scoped curriculum")
    revision = service.session.get(SourceRevision, record["source_revision_id"])
    if revision is None or revision.checksum != record["source_checksum"]:
        raise ScopeError("Correspondence source identity or checksum mismatch")
    service._require_curriculum_revision(revision, "alignment")
    nodes = [service.session.get(CurriculumNode, record[key]) for key in ("left_id", "right_id")]
    if record["left_id"] == record["right_id"] or any(node is None for node in nodes):
        raise ScopeError("Correspondence requires two existing distinct nodes")
    left, right = nodes
    assert left is not None and right is not None
    if left.code != record["left_code"] or right.code != record["right_code"]:
        raise ScopeError("Correspondence endpoint identity mismatch")
    for node in (left, right):
        if node.curriculum_version_id != version.id:
            raise ScopeError("Correspondence crosses curriculum version")
        matches = list(
            service.session.scalars(
                select(CurriculumNode.id)
                .where(
                    CurriculumNode.curriculum_version_id == version.id,
                    CurriculumNode.code == node.code,
                )
                .limit(2)
            )
        )
        if matches != [node.id]:
            raise ScopeError("Correspondence declaration has ambiguous endpoint code")
        validate_entity_scope(
            service, version, revision, node.metadata_json, node_type=node.node_type
        )
        service._validate_scoped_ancestors(version, node, node.metadata_json["identity"])
    left_scope, right_scope = left.metadata_json["identity"], right.metadata_json["identity"]
    if any(
        left_scope[field] != right_scope[field]
        for field in (
            "grade",
            "subject",
            "course_family",
            "course_group",
            "language_role",
            "book_part",
            "bilingual",
        )
    ):
        raise ScopeError("Cross-medium correspondence cannot change academic context")
    if left_scope["medium"] == right_scope["medium"] or left.node_type != right.node_type:
        raise ScopeError("Correspondence must link same-level content in different media")
    declaration = {
        field: record[field] for field in ("left_code", "right_code", "locator", "evidence_text")
    }
    if declaration not in service._source_metadata(revision).get("correspondences", []):
        raise ScopeError("No reviewed source declaration establishes this correspondence")
    try:
        require_source_wording(
            service.source_service,
            revision,
            locator=record["locator"],
            official_text=record["evidence_text"],
        )
        require_endpoint_mentions(
            record["evidence_text"],
            left_codes=(left.code, left.metadata_json.get("official_code", "")),
            left_text=left.official_text,
            right_codes=(right.code, right.metadata_json.get("official_code", "")),
            right_text=right.official_text,
        )
    except StandardsEvidenceError as exc:
        raise ScopeError(str(exc)) from exc
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def link_correspondence(
    service: CurriculumIntelligenceService,
    version: CurriculumVersion,
    *,
    left_node_id: str,
    right_node_id: str,
    revision: SourceRevision,
    locator: str,
    evidence_text: str,
) -> str:
    """Persist only the same bounded proof independently checked by acceptance."""
    from app.models.curriculum import CurriculumNode

    left = service.session.get(CurriculumNode, left_node_id)
    right = service.session.get(CurriculumNode, right_node_id)
    if left is None or right is None:
        raise ScopeError("Correspondence requires two existing distinct nodes")
    record = {
        "left_code": left.code,
        "right_code": right.code,
        "locator": locator,
        "evidence_text": evidence_text,
        "left_id": left.id,
        "right_id": right.id,
        "source_revision_id": revision.id,
        "source_checksum": revision.checksum,
    }
    key = validate_correspondence_record(service, version, record)
    metadata = dict(version.metadata_json)
    links = dict(metadata.get("cross_medium_correspondences", {}))
    if key in links and links[key] != record:
        raise ScopeError("Correspondence identity collision")
    links[key] = record
    metadata["cross_medium_correspondences"] = links
    version.metadata_json = metadata
    service.session.flush()
    return key


def query_scoped_paths(
    service: CurriculumIntelligenceService,
    *,
    pack_code: str | None,
    version_code: str | None,
    grade: str | None,
    medium: str | None,
    subject: str | None,
    include_historical: bool = False,
    course_family: str | None = None,
    course_group: str | None = None,
    subject_language: str | None = None,
    language_role: str | None = None,
    book_part: str | None = None,
    bilingual: str | None = None,
) -> dict[str, Any]:
    """All dimensions required; historical/current aliases never substitute years."""
    from sqlalchemy import select

    from app.models.curriculum import CurriculumNode, CurriculumPack, CurriculumVersion

    if any(
        value is None or value == "unknown"
        for value in (pack_code, version_code, grade, medium, subject)
    ):
        return {"status": "unknown_scope", "paths": []}
    versions = list(
        service.session.scalars(
            select(CurriculumVersion)
            .join(CurriculumPack)
            .where(
                CurriculumPack.code == pack_code,
                CurriculumVersion.version_code == version_code,
            )
        )
    )
    if len(versions) != 1:
        return {"status": "ambiguous" if versions else "no_match", "paths": []}
    version = versions[0]
    if version.status == "superseded" and not include_historical:
        return {"status": "historical_only", "paths": []}
    paths = []
    unresolved: set[str] = set()
    alternatives: set[tuple[str, ...]] = set()
    dimensions = {
        "course_family": course_family,
        "course_group": course_group,
        "subject_language": subject_language,
        "language_role": language_role,
        "book_part": book_part,
        "bilingual": bilingual,
    }
    for node in service.session.scalars(
        select(CurriculumNode).where(
            CurriculumNode.curriculum_version_id == version.id,
            CurriculumNode.node_type == "concept",
        )
    ):
        identity = node.metadata_json.get("identity", {})
        if all(
            identity.get(k) == v
            for k, v in (("grade", grade), ("medium", medium), ("subject", subject))
        ):
            mismatch = False
            missing: set[str] = set()
            for dimension, expected in dimensions.items():
                actual = identity.get(dimension, "unknown")
                if expected == "unknown" or actual in (None, "unknown"):
                    missing.add(dimension)
                elif expected is None:
                    if actual != "not_applicable":
                        missing.add(dimension)
                elif normalize_label(str(actual)) != normalize_label(expected):
                    mismatch = True
            if mismatch:
                continue
            alternatives.add(tuple(str(identity.get(key, "unknown")) for key in dimensions))
            if missing:
                unresolved.update(missing)
            else:
                paths.append(service.curriculum_path(node.id).model_dump(mode="json"))
    if unresolved:
        return {
            "status": "ambiguous" if len(alternatives) > 1 else "unknown_scope",
            "paths": [],
            "unresolved_dimensions": sorted(unresolved),
        }
    return {
        "status": "matched" if paths else "no_match",
        "paths": paths,
        "version_status": version.status,
        "official_acceptance": False,
    }
