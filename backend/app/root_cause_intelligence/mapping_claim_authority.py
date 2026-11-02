from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import PolicyRegistryEntry
from app.models.source import SourceAuditEvent
from app.models.tenancy import AdminActor
from app.prerequisite_intelligence.authority import (
    RevisionAuthorityRecord,
    load_revision_record,
    revision_is_authorized_for_scope,
)
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.prerequisite_intelligence.stable_ids import stable_audit_ref
from app.root_cause_intelligence.mapping_evidence import (
    mapping_evidence_checksum,
    resolve_approved_source_span,
    source_content_checksum,
    verify_revision_content_integrity,
)
from app.root_cause_intelligence.mapping_registry import MisconceptionConceptMapping

MAPPING_CLAIM_APPROVED_EVENT = "root_cause_mapping_claim_approved"
MAPPING_CLAIM_REVOKED_EVENT = "root_cause_mapping_claim_revoked"
ROOT_CAUSE_MAPPING_CURATORS_KEY = "root_cause_mapping_curators"
ROOT_CAUSE_MAPPING_CURATORS_VERSION = "root-cause-mapping-curators@v1"


class MappingClaimAuthorityError(ValueError):
    """Raised when a mapping-claim approval action is invalid."""


@dataclass(frozen=True, slots=True)
class MappingClaimApprovalContext:
    actor_id: str
    organization_id: str
    institution_id: str
    curriculum_version_id: str
    teacher_id: str | None = None


@dataclass(frozen=True, slots=True)
class MappingClaimWriterContext:
    """Session-attested principal performing the claim write (must match actor_id)."""

    authenticated_actor_external_code: str


def mapping_claim_id(
    *,
    source_revision_id: str,
    misconception_code: str,
    candidate_concept_codes: list[str],
    source_locator: str,
    mapping_registry_version: str,
    mapping_evidence_checksum: str,
    organization_id: str | None = None,
    institution_id: str | None = None,
    curriculum_version_id: str | None = None,
) -> str:
    payload = json.dumps(
        {
            "source_revision_id": source_revision_id,
            "misconception_code": misconception_code,
            "candidate_concept_codes": sorted(str(code) for code in candidate_concept_codes),
            "source_locator": source_locator.strip(),
            "mapping_registry_version": mapping_registry_version,
            "mapping_evidence_checksum": mapping_evidence_checksum,
            "organization_id": organization_id,
            "institution_id": institution_id,
            "curriculum_version_id": curriculum_version_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("root-cause-mapping-claim", payload)


def _curator_actor_authorized(session: Session, actor_id: str) -> bool:
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == ROOT_CAUSE_MAPPING_CURATORS_KEY,
            PolicyRegistryEntry.version == ROOT_CAUSE_MAPPING_CURATORS_VERSION,
            PolicyRegistryEntry.status == "active",
        )
    )
    if row is None:
        return False
    allowed = row.payload_json.get("actor_ids") or []
    if not isinstance(allowed, list):
        return False
    return str(actor_id).strip() in {str(item).strip() for item in allowed if item}


def _curator_admin_actor_active(session: Session, actor_id: str) -> bool:
    if not _curator_actor_authorized(session, actor_id):
        return False
    admin = session.scalar(
        select(AdminActor).where(
            AdminActor.external_code == str(actor_id).strip(),
            AdminActor.active.is_(True),
        )
    )
    return admin is not None


def _verify_curator_principal(
    session: Session,
    actor_id: str,
    approval_context: MappingClaimApprovalContext,
) -> bool:
    if not _curator_admin_actor_active(session, actor_id):
        return False
    admin = session.scalar(
        select(AdminActor).where(
            AdminActor.external_code == str(actor_id).strip(),
            AdminActor.active.is_(True),
        )
    )
    assert admin is not None
    if approval_context.organization_id:
        if not admin.organization_id:
            return False
        if str(admin.organization_id) != str(approval_context.organization_id):
            return False
    if approval_context.institution_id:
        if not admin.institution_id:
            return False
        if str(admin.institution_id) != str(approval_context.institution_id):
            return False
    return True


def claim_scope_matches_graph(
    scope_payload: dict[str, Any], graph_scope: PrerequisiteGraphScope
) -> bool:
    claim_org = scope_payload.get("organization_id")
    claim_inst = scope_payload.get("institution_id")
    claim_cur = scope_payload.get("curriculum_version_id")
    claim_teacher = scope_payload.get("teacher_id")
    public_global = bool(scope_payload.get("public_global"))
    claim_private = any([claim_org, claim_inst, claim_cur, claim_teacher]) and not public_global
    if not claim_private:
        return True
    for _field, claim_val, req_val in (
        ("organization_id", claim_org, graph_scope.organization_id),
        ("institution_id", claim_inst, graph_scope.institution_id),
        ("curriculum_version_id", claim_cur, graph_scope.curriculum_version_id),
        ("teacher_id", claim_teacher, graph_scope.teacher_id),
    ):
        if claim_val:
            if not req_val or str(claim_val) != str(req_val):
                return False
    return True


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
    approval_context: MappingClaimApprovalContext,
    writer: MappingClaimWriterContext,
    request_id: str | None = None,
) -> str:
    actor_id = str(approval_context.actor_id).strip()
    if str(writer.authenticated_actor_external_code).strip() != actor_id:
        raise MappingClaimAuthorityError(
            "mapping claim writer is not authenticated as approval actor"
        )
    if not _verify_curator_principal(session, actor_id, approval_context):
        raise MappingClaimAuthorityError("mapping claim actor is not an authorized curator")
    record = load_revision_record(session, revision_id)
    if record is None:
        raise MappingClaimAuthorityError("source revision is unknown")
    if not verify_revision_content_integrity(session, record):
        raise MappingClaimAuthorityError("source revision content integrity check failed")
    graph_scope = PrerequisiteGraphScope(
        curriculum_version_id=approval_context.curriculum_version_id,
        organization_id=approval_context.organization_id,
        institution_id=approval_context.institution_id,
        teacher_id=approval_context.teacher_id,
    )
    if not revision_is_authorized_for_scope(
        record, graph_scope, approval_context.curriculum_version_id
    ):
        raise MappingClaimAuthorityError("source revision is not authorized for mapping scope")
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
    try:
        excerpt, span_checksum = resolve_approved_source_span(session, record, locator)
    except ValueError as exc:
        raise MappingClaimAuthorityError(str(exc)) from exc
    evidence_checksum = mapping_evidence_checksum(
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=mapping_registry_version,
        source_revision_id=revision_id,
        source_content_checksum=content_checksum,
        source_span_checksum=span_checksum,
    )
    claim_id = mapping_claim_id(
        source_revision_id=revision_id,
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=mapping_registry_version,
        mapping_evidence_checksum=evidence_checksum,
        organization_id=approval_context.organization_id,
        institution_id=approval_context.institution_id,
        curriculum_version_id=approval_context.curriculum_version_id,
    )
    session.add(
        SourceAuditEvent(
            source_id=record.source_id,
            source_revision_id=revision_id,
            event_type=MAPPING_CLAIM_APPROVED_EVENT,
            actor_id=approval_context.actor_id,
            request_id=request_id,
            outcome="success",
            payload_json={
                "claim_id": claim_id,
                "misconception_code": entry.misconception_code,
                "candidate_concept_codes": list(entry.candidate_concept_codes),
                "source_locator": locator,
                "source_span_excerpt": excerpt[:256],
                "source_span_checksum": span_checksum,
                "mapping_registry_version": mapping_registry_version,
                "mapping_evidence_checksum": evidence_checksum,
                "source_content_checksum": content_checksum,
                "source_approval_fingerprint": record.approval_fingerprint,
                "approved_by": approval_context.actor_id,
                "organization_id": approval_context.organization_id,
                "institution_id": approval_context.institution_id,
                "curriculum_version_id": approval_context.curriculum_version_id,
                "teacher_id": approval_context.teacher_id,
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
    if not _curator_admin_actor_active(session, actor_id):
        raise MappingClaimAuthorityError("mapping claim actor is not an authorized curator")
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


def _expected_evidence_checksum(
    record: RevisionAuthorityRecord,
    entry: MisconceptionConceptMapping,
    overlay: dict[str, Any],
    *,
    registry_version: str,
) -> str | None:
    locator = str(overlay.get("source_locator") or "").strip()
    content_checksum = source_content_checksum(record)
    span_checksum = str(overlay.get("source_span_checksum") or "").strip()
    if not locator or not content_checksum or not span_checksum:
        return None
    return mapping_evidence_checksum(
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=registry_version,
        source_revision_id=record.revision_id,
        source_content_checksum=content_checksum,
        source_span_checksum=span_checksum,
    )


def _active_mapping_claim_audit(
    session: Session,
    *,
    revision_id: str,
    entry: MisconceptionConceptMapping,
    overlay: dict[str, Any],
    registry_version: str,
    record: RevisionAuthorityRecord,
    expected_evidence_checksum: str,
    graph_scope: PrerequisiteGraphScope,
) -> SourceAuditEvent | None:
    locator = str(overlay.get("source_locator") or "").strip()
    span_checksum = str(overlay.get("source_span_checksum") or "").strip()
    content_checksum = source_content_checksum(record)
    if not content_checksum or not locator or not span_checksum:
        return None
    if not verify_revision_content_integrity(session, record):
        return None
    try:
        _, resolved_span = resolve_approved_source_span(session, record, locator)
    except ValueError:
        return None
    if resolved_span != span_checksum:
        return None
    claim_id = mapping_claim_id(
        source_revision_id=revision_id,
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=registry_version,
        mapping_evidence_checksum=expected_evidence_checksum,
        organization_id=str(overlay.get("organization_id") or graph_scope.organization_id or ""),
        institution_id=str(overlay.get("institution_id") or graph_scope.institution_id or ""),
        curriculum_version_id=str(
            overlay.get("curriculum_version_id") or graph_scope.curriculum_version_id or ""
        ),
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
        if str(payload.get("source_span_checksum") or "") != span_checksum:
            continue
        if str(payload.get("source_approval_fingerprint") or "") != str(
            record.approval_fingerprint
        ):
            continue
        if not str(payload.get("approved_by") or "").strip():
            continue
        if not _curator_admin_actor_active(session, str(payload.get("approved_by") or "")):
            continue
        if not claim_scope_matches_graph(payload, graph_scope):
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
    graph_scope: PrerequisiteGraphScope,
) -> bool:
    locator = str(overlay.get("source_locator") or "").strip()
    if not locator:
        return False
    content_checksum = source_content_checksum(record)
    if not content_checksum:
        return False
    if not record.approval_fingerprint or not record.approved_by:
        return False
    if not verify_revision_content_integrity(session, record):
        return False
    expected_checksum = _expected_evidence_checksum(
        record, entry, overlay, registry_version=registry_version
    )
    if expected_checksum is None:
        return False
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
        graph_scope=graph_scope,
    )
    return claim_event is not None
