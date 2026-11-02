from __future__ import annotations

import hashlib
import json

from app.prerequisite_intelligence.authority import RevisionAuthorityRecord
from app.prerequisite_intelligence.stable_ids import stable_audit_ref


def source_content_checksum(record: RevisionAuthorityRecord) -> str | None:
    if record.validated_checksum:
        return str(record.validated_checksum)
    if record.extracted_checksum:
        return str(record.extracted_checksum)
    return None


def source_span_checksum(excerpt: str) -> str:
    normalized = excerpt.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def resolve_approved_source_span(
    record: RevisionAuthorityRecord, locator: str
) -> tuple[str, str]:
    """Resolve locator to excerpt text bound in approved revision metadata."""
    needle = locator.strip()
    if not needle:
        raise ValueError("locator is empty")
    metadata = record.metadata_json or {}
    manual = metadata.get("manual_metadata")
    if isinstance(manual, dict):
        manual_locator = str(manual.get("locator") or "").strip()
        if manual_locator == needle:
            excerpt = str(manual.get("excerpt") or "").strip()
            if not excerpt:
                raise ValueError("approved source span excerpt is missing")
            return excerpt, source_span_checksum(excerpt)
    extracted = str(metadata.get("extracted_text") or "").strip()
    if not extracted:
        extracted = str((metadata.get("manual_metadata") or {}).get("excerpt") or "").strip()
    if extracted and needle in extracted:
        start = extracted.index(needle)
        excerpt = extracted[start : start + min(len(extracted) - start, 512)].strip()
        if excerpt:
            return excerpt, source_span_checksum(excerpt)
    raise ValueError("locator does not resolve to approved source span")


def mapping_evidence_checksum(
    *,
    misconception_code: str,
    candidate_concept_codes: list[str],
    source_locator: str,
    mapping_registry_version: str,
    source_revision_id: str,
    source_content_checksum: str,
    source_span_checksum: str,
) -> str:
    payload = json.dumps(
        {
            "misconception_code": misconception_code,
            "candidate_concept_codes": sorted(str(code) for code in candidate_concept_codes),
            "source_locator": source_locator.strip(),
            "mapping_registry_version": mapping_registry_version,
            "source_revision_id": source_revision_id,
            "source_content_checksum": source_content_checksum,
            "source_span_checksum": source_span_checksum,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("root-cause-mapping-evidence", payload)
