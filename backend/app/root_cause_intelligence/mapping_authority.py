from __future__ import annotations

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
        source_ids = [str(item) for item in raw.get("source_revision_ids") or [] if item]
        if not source_ids:
            continue
        synthetic_flag = bool(raw.get("synthetic", False))
        if synthetic_flag:
            continue
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
) -> bool:
    if session is None:
        return False
    if entry.synthetic:
        return False
    if not entry.source_revision_ids:
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
