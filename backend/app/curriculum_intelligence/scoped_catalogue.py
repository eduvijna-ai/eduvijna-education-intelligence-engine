"""Revision-bound catalogue metadata, never governing syllabus membership.

Extractors supply a complete, reviewed source inventory. This module validates
that inventory and its persistence; byte provenance alone is not a claim that
an extractor understood every row or that linked document contents were read.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import SourceRevisionStatus

if TYPE_CHECKING:
    from app.curriculum_intelligence.scoped_curriculum import SourceCurriculumScope
    from app.curriculum_intelligence.service import CurriculumIntelligenceService
    from app.models.curriculum import CurriculumVersion
    from app.models.source import SourceRevision

UNKNOWN = "unknown"
STORAGE_KEY = "scoped_catalogue_snapshots"


class ScopedCatalogueError(ValueError):
    """Invalid, ambiguous, incomplete or stale catalogue evidence."""


def checked_text(value: str) -> str:
    """Reject loss/corruption; never transliterate or repair official strings."""
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ScopedCatalogueError("Invalid UTF-8 text requires source review") from exc
    if "\ufffd" in value or any(
        unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in value
    ):
        raise ScopedCatalogueError("Corrupt/control text requires source review")
    # Common UTF-8 interpreted as Latin-1/Windows-1252 signatures. Fail closed;
    # a reviewer must return to the source, not auto-repair ambiguous text.
    if any(marker in value for marker in ("Ã", "Â", "â€", "à°", "à±", "ï¿½")):
        raise ScopedCatalogueError("Possible mojibake requires source review")
    if not value.strip():
        raise ScopedCatalogueError("Empty text requires explicit unknown state")
    return value


def decode_utf8(content: bytes) -> str:
    try:
        return checked_text(content.decode("utf-8-sig", errors="strict"))
    except UnicodeError as exc:
        raise ScopedCatalogueError("Invalid UTF-8 source requires review") from exc


def normalize_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", checked_text(value)).casefold().split())


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CourseApplicability(_Contract):
    status: Literal["unknown", "explicit_groups", "explicit_all"] = "unknown"
    groups: tuple[str, ...] = ()
    source_locator: str | None = None

    @model_validator(mode="after")
    def valid_scope(self) -> CourseApplicability:
        if self.status == "unknown":
            if self.groups or self.source_locator:
                raise ValueError("Unknown applicability cannot assert groups or evidence")
        elif not self.source_locator or not self.source_locator.strip():
            raise ValueError("Explicit applicability requires a source locator")
        elif self.status == "explicit_groups" and not self.groups:
            raise ValueError("Explicit group applicability requires groups")
        elif self.status == "explicit_all" and self.groups:
            raise ValueError("Explicit all must not carry partial groups")
        keys = [normalize_label(group) for group in self.groups]
        if UNKNOWN in keys or len(keys) != len(set(keys)):
            raise ValueError("Unknown or duplicate normalized course group")
        return self

    def allows(self, group: str) -> bool:
        if normalize_label(group) == UNKNOWN or self.status == "unknown":
            return False
        return self.status == "explicit_all" or normalize_label(group) in {
            normalize_label(item) for item in self.groups
        }


class ScopedCatalogueRow(_Contract):
    pack_id: str
    version_id: str
    source_revision_id: str
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_locator: str
    official_label: str
    aliases: tuple[str, ...] = ()
    resource_url: str | None = None
    grade: str = UNKNOWN
    academic_year: str = UNKNOWN
    instructional_medium: str = UNKNOWN
    subject: str = UNKNOWN
    subject_language: str = UNKNOWN
    language_role: Literal["unknown", "first", "second", "third", "not_applicable"] = "unknown"
    book_part: str = UNKNOWN
    bilingual: Literal["unknown", "yes", "no"] = "unknown"
    course_family: str = UNKNOWN
    applicability: CourseApplicability = Field(default_factory=CourseApplicability)
    resource_kind: Literal[
        "textbook",
        "syllabus_index",
        "syllabus_document",
        "assessment",
        "unknown",
        "learning_outcome",
        "academic_standard",
        "pedagogy",
        "calendar",
        "framework",
        "catalogue",
    ] = "unknown"
    curriculum_membership_effect: Literal["none"] = "none"
    document_content_status: Literal["not_parsed", "reviewed"] = "not_parsed"

    @field_validator(
        "pack_id",
        "version_id",
        "source_revision_id",
        "source_locator",
        "official_label",
        "grade",
        "academic_year",
        "instructional_medium",
        "subject",
        "subject_language",
        "book_part",
        "course_family",
    )
    @classmethod
    def text_is_intact(cls, value: str) -> str:
        return checked_text(value)

    @field_validator("aliases")
    @classmethod
    def valid_aliases(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            checked_text(value)
        return values

    @property
    def normalized_label(self) -> str:
        return normalize_label(self.official_label)

    @property
    def scope_key(self) -> str:
        return _digest(
            {
                name: normalize_label(str(getattr(self, name)))
                for name in (
                    "pack_id",
                    "version_id",
                    "grade",
                    "academic_year",
                    "instructional_medium",
                    "subject",
                    "subject_language",
                    "language_role",
                    "book_part",
                    "bilingual",
                    "course_family",
                )
            }
            | {
                "groups": sorted(normalize_label(g) for g in self.applicability.groups),
                "applicability_status": self.applicability.status,
                "resource_kind": self.resource_kind,
            }
        )

    @property
    def identity(self) -> str:
        return _digest([self.source_revision_id, self.scope_key, self.normalized_label])


class InventoryObservation(_Contract):
    """One observed resource occurrence, including unavailable and duplicate items."""

    source_locator: str
    status: Literal["resolved", "duplicate", "unresolved", "blocked"]
    reason: str
    row_identity: str | None = None

    @model_validator(mode="after")
    def valid_observation(self) -> InventoryObservation:
        checked_text(self.source_locator)
        checked_text(self.reason)
        if (self.status in {"resolved", "duplicate"}) != bool(self.row_identity):
            raise ValueError("Only resolved/duplicate observations reference catalogue rows")
        return self


class CatalogueSnapshot(_Contract):
    source_revision_id: str
    source_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: tuple[ScopedCatalogueRow, ...] = Field(min_length=1)
    # This is an extractor's declaration, never inferred from successful parsing.
    inventory_status: Literal["partial", "complete"] = "partial"
    extraction_method: str
    inventory_observations: tuple[InventoryObservation, ...] = ()

    @model_validator(mode="after")
    def coherent_inventory(self) -> CatalogueSnapshot:
        checked_text(self.extraction_method)
        seen: dict[tuple[str, str], str] = {}
        ids: set[str] = set()
        for row in self.rows:
            if (row.source_revision_id, row.source_checksum) != (
                self.source_revision_id,
                self.source_checksum,
            ):
                raise ValueError("Mixed source revisions/checksums in snapshot")
            if row.identity in ids:
                raise ValueError("Duplicate normalized row identity; preserve originals for review")
            ids.add(row.identity)
            for label in (row.official_label, *row.aliases):
                key = (row.scope_key, normalize_label(label))
                previous = seen.setdefault(key, row.identity)
                if previous != row.identity:
                    raise ValueError("Alias collision within catalogue scope")
        if self.inventory_observations:
            locators: set[str] = set()
            resolved: list[str] = []
            for item in self.inventory_observations:
                if item.source_locator in locators:
                    raise ValueError("Duplicate inventory observation locator")
                locators.add(item.source_locator)
                if item.row_identity is not None and item.row_identity not in ids:
                    raise ValueError("Inventory observation references missing row")
                if item.status == "resolved":
                    assert item.row_identity is not None
                    resolved.append(item.row_identity)
                if self.inventory_status == "complete" and item.status in {"unresolved", "blocked"}:
                    raise ValueError("Complete inventory cannot contain unresolved/blocked items")
            if len(resolved) != len(set(resolved)) or set(resolved) != ids:
                raise ValueError("Inventory observations must resolve each unique row exactly once")
        return self

    @property
    def inventory_digest(self) -> str:
        """Source-only extraction identity, available before DB-generated IDs exist."""
        return _digest(
            {
                "source_checksum": self.source_checksum,
                "extraction_method": self.extraction_method,
                "observations": [
                    item.model_dump(exclude={"row_identity"}, mode="json")
                    for item in self.inventory_observations
                ],
                "rows": [
                    row.model_dump(
                        exclude={"pack_id", "version_id", "source_revision_id"}, mode="json"
                    )
                    for row in self.rows
                ],
            }
        )

    @property
    def identity(self) -> str:
        return _digest(self.model_dump(mode="json"))


class CatalogueQuery(_Contract):
    label: str | None = None
    pack_id: str | None = None
    version_id: str | None = None
    grade: str | None = None
    academic_year: str | None = None
    instructional_medium: str | None = None
    subject: str | None = None
    subject_language: str | None = None
    language_role: str | None = None
    book_part: str | None = None
    bilingual: str | None = None
    course_family: str | None = None
    course_group: str | None = None
    resource_kind: str | None = None


class CatalogueQueryResult(_Contract):
    status: Literal["matched", "ambiguous", "unknown_scope", "no_match"]
    rows: tuple[ScopedCatalogueRow, ...] = ()
    unresolved_dimensions: tuple[str, ...] = ()


CATALOGUE_QUERY_DIMENSIONS = (
    "pack_id",
    "version_id",
    "grade",
    "academic_year",
    "instructional_medium",
    "subject",
    "subject_language",
    "language_role",
    "book_part",
    "bilingual",
    "course_family",
    "course_group",
    "resource_kind",
)


def query_catalogue(
    rows: Iterable[ScopedCatalogueRow], query: CatalogueQuery
) -> CatalogueQueryResult:
    """A singleton is not permission to supply any omitted scope dimension."""
    candidates: dict[str, ScopedCatalogueRow] = {}
    uncertain: set[str] = set()
    originals: dict[str, ScopedCatalogueRow] = {}
    for row in rows:
        prior = originals.setdefault(row.identity, row)
        if prior != row:
            raise ScopedCatalogueError("Conflicting rows share a normalized identity")
        if query.label and normalize_label(query.label) not in {
            normalize_label(value) for value in (row.official_label, *row.aliases)
        }:
            continue
        mismatch = False
        missing: set[str] = set()
        for field in CATALOGUE_QUERY_DIMENSIONS:
            value = getattr(query, field)
            if value is None or not value.strip() or normalize_label(value) == UNKNOWN:
                missing.add(field)
                continue
            if field == "course_group":
                if row.applicability.status == "unknown":
                    missing.add(field)
                elif not row.applicability.allows(value):
                    mismatch = True
                continue
            observed = normalize_label(str(getattr(row, field)))
            if observed == UNKNOWN:
                missing.add(field)
            elif observed != normalize_label(value):
                mismatch = True
        if mismatch:
            continue
        if missing:
            uncertain.update(missing)
        else:
            candidates[row.identity] = row
    if uncertain:
        return CatalogueQueryResult(
            status="unknown_scope", unresolved_dimensions=tuple(sorted(uncertain))
        )
    values = tuple(candidates.values())
    return CatalogueQueryResult(
        status="no_match" if not values else "matched" if len(values) == 1 else "ambiguous",
        rows=values,
    )


def validate_catalogue_row_scope(
    version: CurriculumVersion, row: ScopedCatalogueRow, scope: SourceCurriculumScope
) -> None:
    """Shared write/read guard: every materialized claim needs approved exact scope.

    Unknown scope belongs in unresolved inventory observations, not asserted rows.
    A label is never inferred to be a subject, and groups never imply universal scope.
    """
    if (
        row.pack_id != version.curriculum_pack_id
        or row.version_id != version.id
        or scope.pack_code != version.curriculum_pack.code
        or version.version_code not in scope.version_codes
    ):
        raise ScopedCatalogueError("Catalogue evidence crosses pack/version scope")
    if row.academic_year == UNKNOWN or row.academic_year != version.academic_year:
        raise ScopedCatalogueError("Catalogue evidence crosses academic_year scope")
    for field, allowed in (
        ("grade", scope.grades),
        ("instructional_medium", scope.media),
        ("subject", scope.subjects),
        ("course_family", scope.course_families),
        ("subject_language", scope.subject_languages),
        ("language_role", scope.language_roles),
        ("book_part", scope.book_parts),
        ("bilingual", scope.bilingual_states),
    ):
        value = getattr(row, field)
        if value == UNKNOWN or value not in allowed:
            raise ScopedCatalogueError(f"Catalogue evidence crosses {field} scope")
    if row.applicability.status != "explicit_groups" or any(
        group not in scope.course_groups for group in row.applicability.groups
    ):
        raise ScopedCatalogueError("Catalogue evidence crosses course_group scope")


def validate_catalogue_row_locators(
    service: CurriculumIntelligenceService, revision: SourceRevision, row: ScopedCatalogueRow
) -> None:
    """Prove both locators exist in original bytes, independently of scope semantics."""
    from app.curriculum_intelligence.standards_evidence import source_text_at_locator

    source_text_at_locator(service.source_service, revision, locator=row.source_locator)
    source_text_at_locator(
        service.source_service, revision, locator=row.applicability.source_locator
    )


class CatalogueCoverage(_Contract):
    status: Literal["complete", "partial", "failed"]
    snapshot_row_count: int
    materialized_metadata_count: int
    inventory_observation_count: int = 0
    resolved_observation_count: int = 0
    duplicate_observation_count: int = 0
    unresolved_observation_count: int = 0
    blocked_observation_count: int = 0
    missing_ids: tuple[str, ...] = ()
    unexpected_ids: tuple[str, ...] = ()
    duplicate_ids: tuple[str, ...] = ()
    conflicting_ids: tuple[str, ...] = ()
    governing_syllabus_membership_count: Literal[0] = 0
    complete_curriculum: Literal[False] = False
    source_completeness_verified: Literal[False] = False


def reconcile_coverage(
    snapshot: CatalogueSnapshot | None, materialized_rows: Iterable[ScopedCatalogueRow]
) -> CatalogueCoverage:
    actual = list(materialized_rows)
    expected = {row.identity: row for row in snapshot.rows} if snapshot else {}
    observed: dict[str, ScopedCatalogueRow] = {}
    duplicates: set[str] = set()
    conflicts: set[str] = set()
    for row in actual:
        if row.identity in observed:
            duplicates.add(row.identity)
        observed[row.identity] = row
        if row.identity in expected and row != expected[row.identity]:
            conflicts.add(row.identity)
    missing = set(expected) - set(observed)
    extra = set(observed) - set(expected)
    failed = not snapshot or not expected or bool(missing or extra or duplicates or conflicts)
    return CatalogueCoverage(
        status="failed"
        if failed
        else "complete"
        if snapshot and snapshot.inventory_status == "complete"
        else "partial",
        snapshot_row_count=len(expected),
        materialized_metadata_count=len(observed),
        inventory_observation_count=len(snapshot.inventory_observations) if snapshot else 0,
        **{
            f"{status}_observation_count": sum(
                item.status == status for item in snapshot.inventory_observations
            )
            if snapshot
            else 0
            for status in ("resolved", "duplicate", "unresolved", "blocked")
        },
        missing_ids=tuple(sorted(missing)),
        unexpected_ids=tuple(sorted(extra)),
        duplicate_ids=tuple(sorted(duplicates)),
        conflicting_ids=tuple(sorted(conflicts)),
    )


def materialize_catalogue(
    service: CurriculumIntelligenceService,
    version: CurriculumVersion,
    revision: SourceRevision,
    snapshot: CatalogueSnapshot,
) -> CatalogueCoverage:
    """Persist immutable metadata only after Day-3 exact source-byte guards.

    No CurriculumNode or syllabus link is created, even for a syllabus index.
    Semantic completeness remains the responsibility of the inventory extractor.
    """
    if version.status == "superseded":
        raise ScopedCatalogueError("Historical catalogue versions are read-only")
    # model_copy/model_construct can bypass validation; never persist unchecked models.
    snapshot = CatalogueSnapshot.model_validate(snapshot.model_dump(mode="json"))
    if revision.status != SourceRevisionStatus.ACTIVE.value:
        raise ScopedCatalogueError("Catalogue requires active source revision")
    if not service.has_source_content(revision) or not revision.storage_path:
        raise ScopedCatalogueError("Exact extracted source bytes are unavailable")
    checked_text(revision.extracted_text or "")
    content = service.source_service.storage.read(revision.storage_path)
    if hashlib.sha256(content).hexdigest() != revision.checksum:
        raise ScopedCatalogueError("Stored source checksum mismatch")
    source_metadata = service._source_metadata(revision)
    if (
        (version.metadata_json or {}).get("scope_enforced")
        or "inventory_scope" in source_metadata
        or "curriculum_scope" in source_metadata
    ):
        # Local import avoids the shared text-validation dependency cycle.
        from app.curriculum_intelligence.scoped_curriculum import (
            SourceCurriculumScope,
            exact_scope,
        )

        if "inventory_scope" in source_metadata:
            # Inventory scope binds catalogue identity but conveys no governing semantics.
            source_snapshot = revision.metadata_json.get("source_snapshot", {})
            if (
                len(content) != revision.byte_size
                or service.source_service._snapshot_checksum(source_snapshot)
                != revision.source_snapshot_checksum
                or not revision.approval_fingerprint
                or revision.approval_fingerprint
                != service.source_service._approval_fingerprint(revision)
            ):
                raise ScopedCatalogueError("Catalogue source evidence changed after approval")
            scope = SourceCurriculumScope.model_validate(source_metadata["inventory_scope"])
        elif "curriculum_scope" in source_metadata:
            scope = exact_scope(service, revision)
        else:
            raise ScopedCatalogueError("Scoped catalogue requires reviewed source inventory scope")
        for row in snapshot.rows:
            validate_catalogue_row_scope(version, row, scope)
            validate_catalogue_row_locators(service, revision, row)
        from app.curriculum_intelligence.standards_evidence import source_text_at_locator

        source_text_at_locator(
            service.source_service, revision, locator=scope.applicability_locator
        )
    if (snapshot.source_revision_id, snapshot.source_checksum) != (revision.id, revision.checksum):
        raise ScopedCatalogueError("Snapshot does not match exact source revision")
    for row in snapshot.rows:
        if row.version_id != version.id or row.pack_id != version.curriculum_pack_id:
            raise ScopedCatalogueError("Cross-pack/version catalogue row")
    metadata = dict(version.metadata_json or {})
    snapshots = dict(metadata.get(STORAGE_KEY, {}))
    record = {
        "snapshot": snapshot.model_dump(mode="json"),
        "snapshot_id": snapshot.identity,
        "rows": [
            row.model_dump(mode="json")
            | {"id": row.identity, "normalized_label": row.normalized_label}
            for row in snapshot.rows
        ],
    }
    previous = snapshots.get(revision.id)
    if previous is not None and previous != record:
        raise ScopedCatalogueError(
            "Existing catalogue revision is immutable; review changed inventory"
        )
    snapshots[revision.id] = record
    metadata[STORAGE_KEY] = snapshots
    version.metadata_json = metadata
    service.session.flush()
    return persisted_catalogue_coverage(version, revision.id)


def persisted_catalogue_coverage(
    version: CurriculumVersion, source_revision_id: str
) -> CatalogueCoverage:
    """Reconcile the saved snapshot against the actual saved metadata identities.

    Missing storage is a failed report; corrupt storage raises rather than
    permitting callers to substitute desired rows for actual materialization.
    """
    record = (version.metadata_json or {}).get(STORAGE_KEY, {}).get(source_revision_id)
    if record is None:
        return reconcile_coverage(None, ())
    snapshot = CatalogueSnapshot.model_validate(record["snapshot"])
    if (
        snapshot.source_revision_id != source_revision_id
        or record.get("snapshot_id") != snapshot.identity
    ):
        raise ScopedCatalogueError("Stored catalogue snapshot identity mismatch")
    actual = []
    for stored in record.get("rows", []):
        values = dict(stored)
        identity = values.pop("id", None)
        normalized = values.pop("normalized_label", None)
        row = ScopedCatalogueRow.model_validate(values)
        if identity != row.identity or normalized != row.normalized_label:
            raise ScopedCatalogueError("Stored catalogue row identity/label mismatch")
        if row.pack_id != version.curriculum_pack_id or row.version_id != version.id:
            raise ScopedCatalogueError("Stored catalogue row crosses pack/version")
        actual.append(row)
    return reconcile_coverage(snapshot, actual)
