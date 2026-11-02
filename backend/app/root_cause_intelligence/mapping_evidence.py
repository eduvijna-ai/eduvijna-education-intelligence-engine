from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.prerequisite_intelligence.authority import RevisionAuthorityRecord
from app.prerequisite_intelligence.stable_ids import stable_audit_ref
from app.source_intelligence.approval_fingerprint import compute_revision_approval_fingerprint


def source_content_checksum(record: RevisionAuthorityRecord) -> str | None:
    if record.validated_checksum:
        return str(record.validated_checksum)
    if record.extracted_checksum:
        return str(record.extracted_checksum)
    return None


def source_span_checksum(excerpt: str) -> str:
    normalized = excerpt.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _approved_content_digest(record: RevisionAuthorityRecord) -> str | None:
    metadata = record.metadata_json or {}
    manual = metadata.get("manual_metadata")
    if isinstance(manual, dict):
        return hashlib.sha256(_canonical_json_bytes(manual)).hexdigest()
    text = str(record.extracted_text or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_revision_content_integrity(
    session: Session, record: RevisionAuthorityRecord
) -> bool:
    """Ensure checksums and approval fingerprint still match approved source content."""
    digest = _approved_content_digest(record)
    if not digest:
        return False
    stored = source_content_checksum(record)
    if not stored:
        return False
    if digest != stored:
        return False
    if not record.approval_fingerprint:
        return False
    from app.models.source import SourceRevision

    revision = session.get(SourceRevision, record.revision_id)
    if revision is None:
        return False
    current_fingerprint = compute_revision_approval_fingerprint(session, revision)
    if current_fingerprint != str(record.approval_fingerprint):
        return False
    return True


def resolve_approved_source_span(
    session: Session, record: RevisionAuthorityRecord, locator: str
) -> tuple[str, str]:
    """Resolve locator to excerpt text bound in approved extracted source content only."""
    needle = locator.strip()
    if not needle:
        raise ValueError("locator is empty")
    if not verify_revision_content_integrity(session, record):
        raise ValueError("approved source content integrity check failed")
    extracted = str(record.extracted_text or "").strip()
    if not extracted:
        raise ValueError("approved source extraction text is missing")
    if needle not in extracted:
        raise ValueError("locator does not resolve to approved source span")
    start = extracted.index(needle)
    excerpt = extracted[start : start + min(len(extracted) - start, 512)].strip()
    if not excerpt:
        raise ValueError("approved source span excerpt is empty")
    metadata = record.metadata_json or {}
    manual = metadata.get("manual_metadata")
    if isinstance(manual, dict):
        manual_excerpt = str(manual.get("excerpt") or "").strip()
        if manual_excerpt and manual_excerpt not in extracted:
            raise ValueError("mutable source metadata excerpt is not grounded in extraction")
    return excerpt, source_span_checksum(excerpt)


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
