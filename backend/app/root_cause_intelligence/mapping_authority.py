from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import PolicyRegistryEntry
from app.models.enums import SourceRevisionStatus
from app.prerequisite_intelligence.authority import (
    load_revision_record,
    revision_is_authorized_for_scope,
)
from app.prerequisite_intelligence.contracts import PrerequisiteGraphScope
from app.prerequisite_intelligence.stable_ids import stable_audit_ref
from app.root_cause_intelligence.enums import DEFAULT_ROOT_CAUSE_MAPPING_VERSION
from app.root_cause_intelligence.mapping_registry import (
    MisconceptionConceptMapping,
    RootCauseMappingRegistry,
)

ROOT_CAUSE_MAPPING_AUTHORITY_KEY = "root_cause_mapping_authority"
ROOT_CAUSE_MAPPING_AUTHORITY_VERSION = "root-cause-mapping-authority@v1"


def _overlay_payload(session: Session) -> dict[str, Any] | None:
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == ROOT_CAUSE_MAPPING_AUTHORITY_KEY,
            PolicyRegistryEntry.version == ROOT_CAUSE_MAPPING_AUTHORITY_VERSION,
            PolicyRegistryEntry.status == "active",
        )
    )
    if row is None:
        return None
    return dict(row.payload_json or {})


def _normalized_codes(codes: list[str]) -> tuple[str, ...]:
    return tuple(sorted(str(code) for code in codes if code))


def mapping_evidence_checksum(
    *,
    misconception_code: str,
    candidate_concept_codes: list[str],
    source_locator: str,
    mapping_registry_version: str,
) -> str:
    payload = json.dumps(
        {
            "misconception_code": misconception_code,
            "candidate_concept_codes": sorted(str(code) for code in candidate_concept_codes),
            "source_locator": source_locator.strip(),
            "mapping_registry_version": mapping_registry_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return stable_audit_ref("root-cause-mapping-evidence", payload)


def _revision_supports_mapping_binding(
    record_metadata: dict[str, Any],
    entry: MisconceptionConceptMapping,
    overlay: dict[str, Any],
    *,
    registry_version: str,
) -> bool:
    locator = str(overlay.get("source_locator") or "").strip()
    expected_checksum = str(overlay.get("mapping_evidence_checksum") or "").strip()
    if not locator or not expected_checksum:
        return False
    if expected_checksum != mapping_evidence_checksum(
        misconception_code=entry.misconception_code,
        candidate_concept_codes=entry.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=registry_version,
    ):
        return False
    bindings_raw = record_metadata.get("root_cause_mapping_bindings") or []
    if not isinstance(bindings_raw, list):
        return False
    for raw in bindings_raw:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("misconception_code") or "") != entry.misconception_code:
            continue
        if _normalized_codes(list(raw.get("candidate_concept_codes") or [])) != _normalized_codes(
            entry.candidate_concept_codes
        ):
            continue
        if str(raw.get("source_locator") or "").strip() != locator:
            continue
        if str(raw.get("mapping_registry_version") or "") != registry_version:
            continue
        if str(raw.get("mapping_evidence_checksum") or "") != expected_checksum:
            continue
        if str(raw.get("approval_status") or "active").lower() not in {"active", "approved"}:
            continue
        return True
    return False


def _overlay_matches_entry(
    raw: dict[str, Any],
    base: MisconceptionConceptMapping,
    *,
    registry_version: str,
) -> bool:
    if str(raw.get("misconception_code") or "") != base.misconception_code:
        return False
    overlay_registry_version = str(
        raw.get("mapping_registry_version") or raw.get("mapping_version") or ""
    )
    if overlay_registry_version != registry_version:
        return False
    overlay_candidates = raw.get("candidate_concept_codes")
    if not isinstance(overlay_candidates, list) or not overlay_candidates:
        return False
    if _normalized_codes(overlay_candidates) != _normalized_codes(
        base.candidate_concept_codes
    ):
        return False
    source_ids = [str(item) for item in raw.get("source_revision_ids") or [] if item]
    if not source_ids:
        return False
    if bool(raw.get("synthetic", False)):
        return False
    locator = str(raw.get("source_locator") or "").strip()
    checksum = str(raw.get("mapping_evidence_checksum") or "").strip()
    if not locator or not checksum:
        return False
    if checksum != mapping_evidence_checksum(
        misconception_code=base.misconception_code,
        candidate_concept_codes=base.candidate_concept_codes,
        source_locator=locator,
        mapping_registry_version=registry_version,
    ):
        return False
    return True


def _find_approved_overlay(
    session: Session,
    entry: MisconceptionConceptMapping,
    *,
    registry_version: str,
) -> dict[str, Any] | None:
    payload = _overlay_payload(session)
    if not payload:
        return None
    overlays_raw = payload.get("overlays")
    overlays: list[Any] = list(overlays_raw) if isinstance(overlays_raw, list) else []
    for raw in overlays:
        if not isinstance(raw, dict):
            continue
        if _overlay_matches_entry(raw, entry, registry_version=registry_version):
            return raw
    return None


def apply_mapping_authority_overlay(
    session: Session | None,
    registry: RootCauseMappingRegistry,
) -> RootCauseMappingRegistry:
    if session is None:
        return registry
    payload = _overlay_payload(session)
    if not payload:
        return registry
    overlays_raw = payload.get("overlays")
    overlays: list[Any] = list(overlays_raw) if isinstance(overlays_raw, list) else []
    if not overlays:
        return registry
    by_code = {entry.misconception_code: entry for entry in registry.mappings}
    for raw in overlays:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("misconception_code") or "")
        if not code or code not in by_code:
            continue
        base = by_code[code]
        if not _overlay_matches_entry(raw, base, registry_version=registry.version):
            continue
        source_ids = [str(item) for item in raw.get("source_revision_ids") or [] if item]
        by_code[code] = base.model_copy(
            update={
                "source_revision_ids": source_ids,
                "synthetic": False,
            }
        )
    return RootCauseMappingRegistry(
        version=registry.version,
        mappings=list(by_code.values()),
    )


def mapping_entry_production_authorized(
    session: Session | None,
    entry: MisconceptionConceptMapping,
    *,
    graph_scope: PrerequisiteGraphScope,
    allowed_option_revision_ids: set[str] | None = None,
    mapping_registry_version: str = DEFAULT_ROOT_CAUSE_MAPPING_VERSION,
) -> bool:
    if session is None:
        return False
    if entry.synthetic:
        return False
    if not entry.source_revision_ids:
        return False
    approved_overlay = _find_approved_overlay(
        session, entry, registry_version=mapping_registry_version
    )
    if approved_overlay is None:
        return False
    overlay_revision_ids = {
        str(item) for item in approved_overlay.get("source_revision_ids") or [] if item
    }
    if set(entry.source_revision_ids) != overlay_revision_ids:
        return False
    curriculum_version_id = graph_scope.curriculum_version_id
    for revision_id in entry.source_revision_ids:
        revision_key = str(revision_id)
        record = load_revision_record(session, revision_key)
        if record is None:
            return False
        if record.status != SourceRevisionStatus.ACTIVE.value:
            return False
        if not revision_is_authorized_for_scope(record, graph_scope, curriculum_version_id):
            return False
        if (
            allowed_option_revision_ids is not None
            and revision_key not in allowed_option_revision_ids
        ):
            return False
        if not _revision_supports_mapping_binding(
            record.metadata_json or {},
            entry,
            approved_overlay,
            registry_version=mapping_registry_version,
        ):
            return False
    return True


def authorized_mapping_revision_ids(
    entry: MisconceptionConceptMapping,
    allowed_option_revision_ids: set[str],
) -> list[str]:
    return sorted(
        str(revision_id)
        for revision_id in entry.source_revision_ids
        if str(revision_id) in allowed_option_revision_ids
    )
