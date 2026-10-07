"""Day 5 manifest evidence roles and frozen source-identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from app.curriculum_intelligence.source_domains import source_domain
from app.models.enums import SourceType
from app.schemas.curriculum_intelligence import OfficialSourceManifestEntry

ManifestEvidenceRole = Literal["required_academic", "supplemental_authority"]


@dataclass(frozen=True, slots=True)
class FrozenSourceIdentity:
    key: str
    url: str
    source_type: SourceType
    document_type: str


# Compatibility name retained for existing callers/tests.
FrozenSupplementalAuthority = FrozenSourceIdentity


@dataclass(frozen=True, slots=True)
class ManifestClassificationError(Exception):
    source_key: str
    url: str
    reason: str

    def __str__(self) -> str:
        return self.reason


def canonical_retrieval_url(url: str) -> str:
    """Return the HTTP retrieval identity used for duplicate/source binding checks.

    URL fragments never reach the server and therefore cannot distinguish source
    identities. Scheme/host/default-port spelling is normalized while path/query
    remain exact because they can select different official resources.
    """
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not scheme or not hostname:
        raise ValueError("manifest URL must be an absolute URL")
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    port = parsed.port
    if port is not None and (scheme, port) not in {("http", 80), ("https", 443)}:
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))


def _load_frozen_identities(
    scope: dict[str, Any],
    field: str,
) -> tuple[FrozenSourceIdentity, ...]:
    raw = scope.get(field)
    if not isinstance(raw, list):
        raise ManifestClassificationError(
            f"<scope:{field}>",
            "",
            f"{field} must be a list of frozen source identities",
        )
    records: list[FrozenSourceIdentity] = []
    for index, item in enumerate(raw):
        marker = f"<scope:{field}[{index}]>"
        if not isinstance(item, dict):
            raise ManifestClassificationError(
                marker,
                "",
                f"{field} entries must be objects",
            )
        try:
            key = item["key"]
            url = item["url"]
            source_type = item["source_type"]
            document_type = item["document_type"]
        except KeyError as exc:
            raise ManifestClassificationError(
                marker,
                str(item.get("url", "")),
                f"{field} entry missing required field {exc.args[0]}",
            ) from exc
        if not all(isinstance(value, str) and value.strip() for value in (key, url, document_type)):
            raise ManifestClassificationError(
                str(key or marker),
                str(url or ""),
                f"{field} identity fields must be non-empty strings",
            )
        try:
            source_type_value = SourceType(str(source_type))
            canonical_retrieval_url(str(url))
        except (TypeError, ValueError) as exc:
            raise ManifestClassificationError(
                str(key),
                str(url),
                f"{field} entry is invalid: {exc}",
            ) from exc
        records.append(
            FrozenSourceIdentity(
                key=str(key),
                url=str(url),
                source_type=source_type_value,
                document_type=str(document_type),
            )
        )

    keys = [record.key for record in records]
    urls = [canonical_retrieval_url(record.url) for record in records]
    if len(keys) != len(set(keys)) or len(urls) != len(set(urls)):
        raise ManifestClassificationError(
            f"<scope:{field}>",
            "",
            f"{field} identities must have unique keys and canonical retrieval URLs",
        )
    return tuple(records)


def load_frozen_supplemental_authorities(
    scope: dict[str, Any],
) -> tuple[FrozenSupplementalAuthority, ...]:
    return _load_frozen_identities(scope, "frozen_supplemental_authority_sources")


def load_frozen_required_academic_sources(
    scope: dict[str, Any],
) -> tuple[FrozenSourceIdentity, ...]:
    return _load_frozen_identities(scope, "frozen_required_academic_sources")


def validate_manifest_identity(
    entries: list[OfficialSourceManifestEntry],
) -> tuple[list[OfficialSourceManifestEntry], list[dict[str, Any]]]:
    """Reject duplicate keys or canonical retrieval identities before ingestion."""
    blockers: list[dict[str, Any]] = []
    seen_keys: dict[str, str] = {}
    seen_urls: dict[str, str] = {}
    validated: list[OfficialSourceManifestEntry] = []
    for entry in entries:
        try:
            canonical_url = canonical_retrieval_url(entry.url)
        except ValueError as exc:
            blockers.append(
                {
                    "stage": "manifest_identity",
                    "source_key": entry.key,
                    "url": entry.url,
                    "reason": str(exc),
                    "affected_tasks": ["D5-03", "D5-05"],
                }
            )
            continue
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
        if canonical_url in seen_urls and seen_urls[canonical_url] != entry.key:
            blockers.append(
                {
                    "stage": "manifest_identity",
                    "source_key": entry.key,
                    "url": entry.url,
                    "reason": "Manifest URL already bound to a different source key",
                    "conflicts_with_key": seen_urls[canonical_url],
                    "canonical_retrieval_url": canonical_url,
                    "affected_tasks": ["D5-03", "D5-05"],
                }
            )
            continue
        seen_keys[entry.key] = entry.url
        seen_urls[canonical_url] = entry.key
        validated.append(entry)
    return validated, blockers


def validate_required_manifest_contract(
    entries: list[OfficialSourceManifestEntry],
    scope: dict[str, Any],
) -> tuple[tuple[FrozenSourceIdentity, ...], list[dict[str, Any]]]:
    """Compare the submitted manifest with the independently frozen required set."""
    blockers: list[dict[str, Any]] = []
    try:
        frozen_required = load_frozen_required_academic_sources(scope)
    except ManifestClassificationError as exc:
        return (), [
            {
                "stage": "manifest_required_contract",
                "source_key": exc.source_key,
                "url": exc.url,
                "reason": exc.reason,
                "affected_tasks": ["D5-03", "D5-05", "D5-22"],
            }
        ]
    try:
        frozen_supplemental = load_frozen_supplemental_authorities(scope)
    except ManifestClassificationError as exc:
        frozen_supplemental = ()
        blockers.append(
            {
                "stage": "manifest_required_contract",
                "source_key": exc.source_key,
                "url": exc.url,
                "reason": exc.reason,
                "affected_tasks": ["D5-03", "D5-05", "D5-22"],
            }
        )

    actual_by_key = {entry.key: entry for entry in entries}
    required_keys = {record.key for record in frozen_required}
    supplemental_keys = {record.key for record in frozen_supplemental}

    for expected in frozen_required:
        actual = actual_by_key.get(expected.key)
        if actual is None:
            blockers.append(
                {
                    "stage": "manifest_required_contract",
                    "source_key": expected.key,
                    "url": expected.url,
                    "reason": "Frozen required academic manifest identity is missing",
                    "affected_tasks": ["D5-03", "D5-05", "D5-22"],
                }
            )
            continue
        try:
            same_url = canonical_retrieval_url(actual.url) == canonical_retrieval_url(expected.url)
        except ValueError:
            same_url = False
        if (
            not same_url
            or actual.source_type != expected.source_type
            or actual.document_type != expected.document_type
        ):
            blockers.append(
                {
                    "stage": "manifest_required_contract",
                    "source_key": expected.key,
                    "url": actual.url,
                    "reason": "Manifest entry contradicts frozen required academic identity",
                    "expected_url": expected.url,
                    "expected_source_type": expected.source_type.value,
                    "expected_document_type": expected.document_type,
                    "affected_tasks": ["D5-03", "D5-05", "D5-22"],
                }
            )

    for entry in entries:
        if entry.key not in required_keys and entry.key not in supplemental_keys:
            blockers.append(
                {
                    "stage": "manifest_required_contract",
                    "source_key": entry.key,
                    "url": entry.url,
                    "reason": "Manifest contains an unfrozen academic/source identity",
                    "affected_tasks": ["D5-03", "D5-05", "D5-22"],
                }
            )
    return frozen_required, blockers


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
        and canonical_retrieval_url(entry.url) == canonical_retrieval_url(frozen.url)
        and entry.source_type == frozen.source_type
        and entry.document_type == frozen.document_type
    )


def manifest_evidence_role(
    entry: OfficialSourceManifestEntry,
    scope: dict[str, Any],
) -> ManifestEvidenceRole:
    """Classify entries using independently frozen supplemental contracts."""
    frozen_records = load_frozen_supplemental_authorities(scope)
    frozen_by_key = {record.key: record for record in frozen_records}
    frozen_by_url = {
        canonical_retrieval_url(record.url): record for record in frozen_records
    }
    canonical_entry_url = canonical_retrieval_url(entry.url)

    url_owner = frozen_by_url.get(canonical_entry_url)
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
    except (KeyError, TypeError, ValueError) as exc:
        return "required_academic", ManifestClassificationError(
            entry.key,
            entry.url,
            str(exc),
        )
