from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source import SourceAuditEvent
from app.prerequisite_intelligence.authority import RevisionAuthorityRecord, load_revision_record
from app.prerequisite_intelligence.stable_ids import stable_audit_ref
from app.root_cause_intelligence.mapping_evidence import (
    mapping_evidence_checksum,
    source_content_checksum,
)
from app.root_cause_intelligence.mapping_registry import MisconceptionConceptMapping

MAPPING_CLAIM_APPROVED_EVENT = "root_cause_mapping_claim_approved"
MAPPING_CLAIM_REVOKED_EVENT = "root_cause_mapping_claim_revoked"


class MappingClaimAuthorityError(ValueError):
    """Raised when a mapping-claim approval action is invalid."""


def mapping_claim_id(
    *,
    source_revision_id: str,
    misconception_code: str,
    candidate_concept_codes: list[str],
    source_locator: str,
    mapping_registry_version: str,
    mapping_evidence_checksum: str,
) -> str:
    payload = json.dumps(
        {
            "source_revision_id": source_revision_id,
            "misconception_code": misconception_code,
            "candidate_concept_codes": sorted(str(code) for code in candidate_concept_codes),
            "source_locator": source_locator.strip(),
            "mapping_registry_version": mapping_registry_version,
            "mapping_evidence_checksum": mapping_evidence_checksum,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("root-cause-mapping-claim", payload)


def _latest_source_approved_audit(
    session: Session, revision_id: str
) -> SourceAuditEvent | None:
    return session.scalar(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == "source_approved",
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    )


def _mapping_claim_revoked(
    session: Session, revision_id: str, claim_id: str, after_event_id: str
) -> bool:
    approved = session.get(SourceAuditEvent, after_event_id)
    if approved is None:
        return True
    revoked = session.scalars(
        select(SourceAuditEvent).where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == MAPPING_CLAIM_REVOKED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
    ).all()
    for event in revoked:
        if event.created_at <= approved.created_at:
            continue
        payload = event.payload_json or {}
        if str(payload.get("claim_id") or "") == claim_id:
            return True
    return False


def approve_root_cause_mapping_claim(
    session: Session,
    *,
    revision_id: str,
    entry: MisconceptionConceptMapping,
    source_locator: str,
    mapping_registry_version: str,
    actor_id: str,
    request_id: str | None = None,
) -> str:
    record = load_revision_record(session, revision_id)
    if record is None:
        raise MappingClaimAuthorityError("source revision is unknown")
    if not record.approval_fingerprint or not record.approved_by:
        raise MappingClaimAuthorityError(
            "source revision lacks genuine source-content approval"
        )
    approved_audit = _latest_source_approved_audit(session, revision_id)
    if approved_audit is None:
        raise MappingClaimAuthorityError(
            "source revision has no persisted source_approved audit event"
        )
    audit_fingerprint = str(
        (approved_audit.payload_json or {}).get("approval_fingerprint") or ""
    )
    if audit_fingerprint != str(record.approval_fingerprint):
        raise MappingClaimAuthorityError(
            "source approval fingerprint does not match source_approved audit"
        )
    content_checksum = source_content_checksum(record)
    if not content_checksum:
        raise MappingClaimAuthorityError("source revision has no content checksum")
    locator = source_locator.strip()
    if not locator:
        raise MappingClaimAuthorityError("mapping claim requires source_locator")
    evidence_checksum = mapping_evidence_checksum(
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=mapping_registry_version,
        source_revision_id=revision_id,
        source_content_checksum=content_checksum,
    )
    claim_id = mapping_claim_id(
        source_revision_id=revision_id,
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=mapping_registry_version,
        mapping_evidence_checksum=evidence_checksum,
    )
    session.add(
        SourceAuditEvent(
            source_id=record.source_id,
            source_revision_id=revision_id,
            event_type=MAPPING_CLAIM_APPROVED_EVENT,
            actor_id=actor_id,
            request_id=request_id,
            outcome="success",
            payload_json={
                "claim_id": claim_id,
                "misconception_code": entry.misconception_code,
                "candidate_concept_codes": list(entry.candidate_concept_codes),
                "source_locator": locator,
                "mapping_registry_version": mapping_registry_version,
                "mapping_evidence_checksum": evidence_checksum,
                "source_content_checksum": content_checksum,
                "source_approval_fingerprint": record.approval_fingerprint,
                "approved_by": actor_id,
                "claim_status": "active",
            },
        )
    )
    session.flush()
    return claim_id


def revoke_root_cause_mapping_claim(
    session: Session,
    *,
    revision_id: str,
    claim_id: str,
    actor_id: str,
    request_id: str | None = None,
) -> None:
    record = load_revision_record(session, revision_id)
    if record is None:
        raise MappingClaimAuthorityError("source revision is unknown")
    session.add(
        SourceAuditEvent(
            source_id=record.source_id,
            source_revision_id=revision_id,
            event_type=MAPPING_CLAIM_REVOKED_EVENT,
            actor_id=actor_id,
            request_id=request_id,
            outcome="success",
            payload_json={"claim_id": claim_id, "claim_status": "revoked"},
        )
    )
    session.flush()


def _active_mapping_claim_audit(
    session: Session,
    *,
    revision_id: str,
    entry: MisconceptionConceptMapping,
    overlay: dict[str, Any],
    registry_version: str,
    record: RevisionAuthorityRecord,
    expected_evidence_checksum: str,
) -> SourceAuditEvent | None:
    locator = str(overlay.get("source_locator") or "").strip()
    content_checksum = source_content_checksum(record)
    if not content_checksum or not locator:
        return None
    claim_id = mapping_claim_id(
        source_revision_id=revision_id,
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=registry_version,
        mapping_evidence_checksum=expected_evidence_checksum,
    )
    events = session.scalars(
        select(SourceAuditEvent)
        .where(
            SourceAuditEvent.source_revision_id == revision_id,
            SourceAuditEvent.event_type == MAPPING_CLAIM_APPROVED_EVENT,
            SourceAuditEvent.outcome == "success",
        )
        .order_by(SourceAuditEvent.created_at.desc())
    ).all()
    for event in events:
        payload = event.payload_json or {}
        if str(payload.get("claim_id") or "") != claim_id:
            continue
        if str(payload.get("misconception_code") or "") != entry.misconception_code:
            continue
        if str(payload.get("mapping_registry_version") or "") != registry_version:
            continue
        if str(payload.get("source_locator") or "").strip() != locator:
            continue
        if str(payload.get("mapping_evidence_checksum") or "") != expected_evidence_checksum:
            continue
        if str(payload.get("source_content_checksum") or "") != content_checksum:
            continue
        if str(payload.get("source_approval_fingerprint") or "") != str(
            record.approval_fingerprint
        ):
            continue
        if not str(payload.get("approved_by") or "").strip():
            continue
        if _mapping_claim_revoked(session, revision_id, claim_id, event.id):
            continue
        return event
    return None


def mapping_claim_authorized_for_overlay(
    session: Session,
    record: RevisionAuthorityRecord,
    entry: MisconceptionConceptMapping,
    overlay: dict[str, Any],
    *,
    registry_version: str,
) -> bool:
    locator = str(overlay.get("source_locator") or "").strip()
    if not locator:
        return False
    content_checksum = source_content_checksum(record)
    if not content_checksum:
        return False
    if not record.approval_fingerprint or not record.approved_by:
        return False
    expected_checksum = mapping_evidence_checksum(
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=registry_version,
        source_revision_id=record.revision_id,
        source_content_checksum=content_checksum,
    )
    overlay_checksum = str(overlay.get("mapping_evidence_checksum") or "").strip()
    if overlay_checksum != expected_checksum:
        return False
    approved_audit = _latest_source_approved_audit(session, record.revision_id)
    if approved_audit is None:
        return False
    audit_fingerprint = str(
        (approved_audit.payload_json or {}).get("approval_fingerprint") or ""
    )
    if audit_fingerprint != str(record.approval_fingerprint):
        return False
    claim_event = _active_mapping_claim_audit(
        session,
        revision_id=record.revision_id,
        entry=entry,
        overlay=overlay,
        registry_version=registry_version,
        record=record,
        expected_evidence_checksum=expected_checksum,
    )
    return claim_event is not None
