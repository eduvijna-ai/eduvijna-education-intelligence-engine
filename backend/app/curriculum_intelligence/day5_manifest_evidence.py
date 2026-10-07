"""Day 5 manifest evidence roles: required academic vs supplemental authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.curriculum_intelligence.source_domains import source_domain
from app.models.enums import SourceType
from app.schemas.curriculum_intelligence import OfficialSourceManifestEntry

ManifestEvidenceRole = Literal["required_academic", "supplemental_authority"]


@dataclass(frozen=True, slots=True)
class FrozenSupplementalAuthority:
    key: str
    url: str
    source_type: SourceType
    document_type: str


@dataclass(frozen=True, slots=True)
class ManifestClassificationError(Exception):
    source_key: str
    url: str
    reason: str

    def __str__(self) -> str:
        return self.reason


def load_frozen_supplemental_authorities(
    scope: dict[str, Any],
) -> tuple[FrozenSupplementalAuthority, ...]:
    raw = scope.get("frozen_supplemental_authority_sources", ())
    records: list[FrozenSupplementalAuthority] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("frozen_supplemental_authority_sources entries must be objects")
        records.append(
            FrozenSupplementalAuthority(
                key=str(item["key"]),
                url=str(item["url"]),
                source_type=SourceType(str(item["source_type"])),
                document_type=str(item["document_type"]),
            )
        )
    keys = [record.key for record in records]
    urls = [record.url for record in records]
    if len(keys) != len(set(keys)) or len(urls) != len(set(urls)):
        raise ValueError("frozen supplemental authority identities must be unique")
    return tuple(records)


def validate_manifest_identity(
    entries: list[OfficialSourceManifestEntry],
) -> tuple[list[OfficialSourceManifestEntry], list[dict[str, Any]]]:
    """Reject duplicate keys or conflicting URL bindings before ingestion."""
    blockers: list[dict[str, Any]] = []
    seen_keys: dict[str, str] = {}
    seen_urls: dict[str, str] = {}
    validated: list[OfficialSourceManifestEntry] = []
    for entry in entries:
        if entry.key in seen_keys:
            blockers.append(
                {
                    "stage": "manifest_identity",
                    "source_key": entry.key,
                    "url": entry.url,
                    "reason": "Duplicate manifest source key",
                    "conflicts_with_url": seen_keys[entry.key],
                    "affected_tasks": ["D5-03", "D5-05"],
                }
            )
            continue
        if entry.url in seen_urls and seen_urls[entry.url] != entry.key:
            blockers.append(
                {
                    "stage": "manifest_identity",
                    "source_key": entry.key,
                    "url": entry.url,
                    "reason": "Manifest URL already bound to a different source key",
                    "conflicts_with_key": seen_urls[entry.url],
                    "affected_tasks": ["D5-03", "D5-05"],
                }
            )
            continue
        seen_keys[entry.key] = entry.url
        seen_urls[entry.url] = entry.key
        validated.append(entry)
    return validated, blockers


def manifest_source_snapshot(entry: OfficialSourceManifestEntry) -> dict[str, Any]:
    metadata = dict(entry.metadata_json or {})
    return {
        "source_type": entry.source_type,
        "metadata_json": {
            "document_type": entry.document_type,
            **metadata,
        },
    }


def _frozen_supplemental_match(
    entry: OfficialSourceManifestEntry,
    frozen: FrozenSupplementalAuthority,
) -> bool:
    return (
        entry.key == frozen.key
        and entry.url == frozen.url
        and entry.source_type == frozen.source_type
        and entry.document_type == frozen.document_type
    )


def manifest_evidence_role(
    entry: OfficialSourceManifestEntry,
    scope: dict[str, Any],
) -> ManifestEvidenceRole:
    """Classify manifest entries using frozen supplemental contracts.

    Supplemental authority status requires an exact frozen key/URL/source_type/
    document_type binding. Relabelled academic sources remain required_academic.
    """
    frozen_records = load_frozen_supplemental_authorities(scope)
    frozen_by_key = {record.key: record for record in frozen_records}
    frozen_by_url = {record.url: record for record in frozen_records}

    url_owner = frozen_by_url.get(entry.url)
    if url_owner is not None and url_owner.key != entry.key:
        raise ManifestClassificationError(
            entry.key,
            entry.url,
            "Manifest URL is frozen to a different supplemental authority key",
        )

    frozen = frozen_by_key.get(entry.key)
    if frozen is None:
        if entry.document_type == "authority_directory":
            raise ManifestClassificationError(
                entry.key,
                entry.url,
                "authority_directory is not a frozen supplemental authority identity",
            )
        return "required_academic"

    if not _frozen_supplemental_match(entry, frozen):
        raise ManifestClassificationError(
            entry.key,
            entry.url,
            "Manifest entry contradicts frozen supplemental authority identity",
        )
    try:
        domain = source_domain(manifest_source_snapshot(entry))
    except ValueError as exc:
        raise ManifestClassificationError(
            entry.key,
            entry.url,
            f"Supplemental authority domain classification invalid: {exc}",
        ) from exc
    if domain != "authority_reference":
        raise ManifestClassificationError(
            entry.key,
            entry.url,
            "Frozen supplemental authority must resolve to authority_reference domain",
        )
    return "supplemental_authority"


def classify_manifest_entry(
    entry: OfficialSourceManifestEntry,
    scope: dict[str, Any],
) -> tuple[ManifestEvidenceRole, ManifestClassificationError | None]:
    try:
        return manifest_evidence_role(entry, scope), None
    except ManifestClassificationError as exc:
        return "required_academic", exc
    except ValueError as exc:
        return "required_academic", ManifestClassificationError(
            entry.key,
            entry.url,
            str(exc),
        )
