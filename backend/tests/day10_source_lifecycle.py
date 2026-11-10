from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.education_intelligence import PolicyRegistryEntry
from app.models.enums import (
    PolicyScopeType,
    SourceExtractionStatus,
    SourceIngestionMethod,
    SourceRevisionStatus,
)
from app.models.policy import PolicyRule
from app.models.source import Source, SourceRevision
from app.models.tenancy import AdminActor, Teacher
from app.paper_distribution.mandatory_policy_resolver import PAPER_MANDATORY_POLICY_KEY
from app.root_cause_intelligence.mapping_claim_authority import (
    ROOT_CAUSE_MAPPING_CURATORS_KEY,
    ROOT_CAUSE_MAPPING_CURATORS_VERSION,
)
from app.source_intelligence.service import SourceIntelligenceService
from app.source_intelligence.storage import LocalSourceStorage

DEFAULT_MAPPING_CURATOR_ACTOR = "educational-curator-day10"


def _canonical_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def ensure_mapping_curator_admin_actor(
    session: Session,
    *,
    organization_id: str,
    institution_id: str,
    external_code: str = DEFAULT_MAPPING_CURATOR_ACTOR,
    display_name: str = "Day10 mapping curator",
) -> AdminActor:
    existing = session.scalar(
        select(AdminActor).where(AdminActor.external_code == external_code)
    )
    if existing is not None:
        return existing
    admin = AdminActor(
        organization_id=organization_id,
        institution_id=institution_id,
        external_code=external_code,
        display_name=display_name,
        active=True,
    )
    session.add(admin)
    session.flush()
    row = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == ROOT_CAUSE_MAPPING_CURATORS_KEY,
            PolicyRegistryEntry.version == ROOT_CAUSE_MAPPING_CURATORS_VERSION,
        )
    )
    if row is not None:
        allowed = list(row.payload_json.get("actor_ids") or [])
        if external_code not in allowed:
            allowed.append(external_code)
            row.payload_json = {**(row.payload_json or {}), "actor_ids": allowed}
            session.flush()
    return admin


def ensure_mapping_curator_registry(session: Session) -> None:
    existing = session.scalar(
        select(PolicyRegistryEntry).where(
            PolicyRegistryEntry.registry_key == ROOT_CAUSE_MAPPING_CURATORS_KEY,
            PolicyRegistryEntry.version == ROOT_CAUSE_MAPPING_CURATORS_VERSION,
        )
    )
    if existing is not None:
        return
    session.add(
        PolicyRegistryEntry(
            registry_key=ROOT_CAUSE_MAPPING_CURATORS_KEY,
            version=ROOT_CAUSE_MAPPING_CURATORS_VERSION,
            status="active",
            payload_json={"actor_ids": [DEFAULT_MAPPING_CURATOR_ACTOR, "founder-day10-trust"]},
        )
    )
    session.flush()


def ensure_genuine_source_content_approval(
    session: Session,
    tmp_path: Path,
    revision_id: str,
    *,
    actor_id: str = "founder-day10-trust",
    source_locator: str,
    storage_root: Path | None = None,
    manual_metadata: dict | None = None,
) -> SourceRevision:
    """Run the real source validate → approve → activate lifecycle for a manual revision."""
    revision = session.get(SourceRevision, revision_id)
    if revision is None:
        raise AssertionError("revision missing")
    source = revision.source
    if not source.authority:
        source.authority = "Synthetic Education Authority"
        session.flush()
    manual_metadata = manual_metadata or {
        "document_type": "official_misconception_mapping_table",
        "locator": source_locator,
        "excerpt": (
            "Whole-number addition off-by-one-low maps to whole-number and multi-step addition."
        ),
    }
    if str(manual_metadata.get("locator") or "") != source_locator:
        manual_metadata = {**manual_metadata, "locator": source_locator}
    content = _canonical_json_bytes(manual_metadata)
    from app.source_intelligence.service import _sha256

    checksum = _sha256(content)
    storage = LocalSourceStorage(storage_root or (tmp_path / "day10-source-store"))
    service = SourceIntelligenceService(session, storage=storage)
    snapshot = service._source_snapshot(source)
    snapshot_checksum = service._snapshot_checksum(snapshot)
    revision.metadata_json = {
        **(revision.metadata_json or {}),
        "manual_metadata": manual_metadata,
        "source_snapshot": snapshot,
    }
    revision.checksum = checksum
    revision.extracted_checksum = checksum
    revision.validated_checksum = None
    revision.byte_size = len(content)
    revision.content_type = "application/json"
    revision.extraction_status = SourceExtractionStatus.SUCCEEDED.value
    revision.extracted_text = json.dumps(manual_metadata, sort_keys=True)
    revision.source_snapshot_checksum = snapshot_checksum
    revision.status = SourceRevisionStatus.EXTRACTED.value
    revision.active_slot = None
    revision.approval_fingerprint = None
    revision.approved_by = None
    revision.approved_at = None
    session.flush()
    service.create_diff(revision.id, actor_id=actor_id)
    validation = service.validate_revision(revision.id, actor_id=actor_id)
    if not validation.valid:
        raise AssertionError(f"source validation failed: {validation.errors}")
    service.approve_revision(revision.id, actor_id=actor_id)
    service.activate_revision(revision.id, actor_id=actor_id)
    session.refresh(revision)
    return revision


def ensure_genuine_json_upload_source_approval(
    session: Session,
    tmp_path: Path,
    *,
    organization_id: str,
    institution_id: str,
    curriculum_version_id: str,
    actor_id: str = "founder-day10-trust",
    source_locator: str,
    storage_root: Path | None = None,
) -> tuple[SourceRevision, str]:
    """Ingest copyright-safe JSON bytes, extract, validate, approve, activate."""
    from app.models.enums import SourceStatus, SourceTrustTier, SourceType

    upload_source = Source(
        organization_id=organization_id,
        institution_id=institution_id,
        source_type=SourceType.INSTITUTION_CONTENT.value,
        title="Day10 JSON misconception mapping upload",
        trust_tier=SourceTrustTier.INSTITUTION.value,
        status=SourceStatus.ACTIVE.value,
        authority="Synthetic Education Authority",
    )
    session.add(upload_source)
    session.flush()
    from app.models.curriculum import CurriculumVersion

    curriculum_version = session.get(CurriculumVersion, curriculum_version_id)
    mapping_payload = {
        "document_type": "official_misconception_mapping_table",
        "locator": source_locator,
        "excerpt": (
            "Whole-number addition off-by-one-low maps to whole-number and multi-step addition."
        ),
        "subject": "Mathematics",
        "grade": 4,
    }
    content = _canonical_json_bytes(mapping_payload)
    store_root = storage_root or (tmp_path / "day10-json-upload-store")
    storage = LocalSourceStorage(store_root)
    service = SourceIntelligenceService(session, storage=storage)
    revision = service.ingest_upload(
        upload_source.id,
        method=SourceIngestionMethod.JSON,
        content=content,
        filename="misconception-mapping.json",
        actor_id=actor_id,
    )
    session.flush()
    if curriculum_version is not None:
        revision.curriculum_versions.append(curriculum_version)
        session.flush()
    service.extract_revision(revision.id, actor_id=actor_id)
    service.create_diff(revision.id, actor_id=actor_id)
    validation = service.validate_revision(revision.id, actor_id=actor_id)
    if not validation.valid:
        raise AssertionError(f"json source validation failed: {validation.errors}")
    service.approve_revision(revision.id, actor_id=actor_id)
    service.activate_revision(revision.id, actor_id=actor_id)
    session.refresh(revision)
    return revision, str(store_root)


def ensure_teacher_for_scope(
    session: Session,
    *,
    institution_id: str,
    external_code: str,
    display_name: str | None = None,
) -> Teacher:
    from app.models.tenancy import Teacher

    existing = session.scalar(
        select(Teacher).where(
            Teacher.institution_id == institution_id,
            Teacher.external_code == external_code,
        )
    )
    if existing is not None:
        existing.active = True
        session.flush()
        return existing
    teacher = Teacher(
        institution_id=institution_id,
        external_code=external_code,
        display_name=display_name or external_code,
        active=True,
    )
    session.add(teacher)
    session.flush()
    return teacher


FICTITIOUS_BOARD_MANDATORY_LOCATOR = "fictitious-board/cognitive-mandatory"
EDUVIJNA_DEMO_BOARD_CODE = "eduvijna-demo-board"


def mandatory_board_policy_rule(
    *,
    value_json: dict,
    source_locator: str,
    scope_code: str = "cbse",
    priority: int = 10,
) -> PolicyRule:
    return PolicyRule(
        scope_type=PolicyScopeType.BOARD.value,
        scope_code=scope_code,
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json=value_json,
        priority=priority,
        active=True,
        metadata_json={"mandatory_source_locator": source_locator},
    )


def ensure_board_mandatory_source_evidence(
    session: Session,
    tmp_path: Path,
    revision_id: str,
    *,
    board_code: str = EDUVIJNA_DEMO_BOARD_CODE,
    source_locator: str = FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    policy_excerpt: str,
    actor_id: str = "founder-day10-trust",
) -> SourceRevision:
    """Approve an official board source with board identity set before source approval."""
    from app.models.enums import SourceTrustTier, SourceType

    revision = session.get(SourceRevision, revision_id)
    if revision is None or revision.source is None:
        raise ValueError("revision or source missing")
    source = revision.source
    source.source_type = SourceType.OFFICIAL_EXAM_BULLETIN.value
    source.trust_tier = SourceTrustTier.OFFICIAL_PRIMARY.value
    source.board_or_exam = str(board_code).strip()
    source.authority = (
        f"Fictitious {board_code.upper()} Education Board (synthetic Day10 fixture)"
    )
    session.flush()
    manual_metadata = {
        "document_type": "official_paper_distribution_mandatory_targets",
        "locator": source_locator,
        "excerpt": policy_excerpt,
    }
    return ensure_genuine_source_content_approval(
        session,
        tmp_path,
        revision_id,
        actor_id=actor_id,
        source_locator=source_locator,
        manual_metadata=manual_metadata,
    )


def bind_revision_board_mandatory_source(
    session: Session, revision_id: str, *, board_code: str
) -> None:
    """Deprecated: mutating board authority after approval is rejected by mandatory policy gates."""
    raise ValueError(
        "bind_revision_board_mandatory_source is disabled; call "
        "ensure_board_mandatory_source_evidence before source approval instead"
    )


def default_board_mandatory_excerpt(
    source_locator: str = FICTITIOUS_BOARD_MANDATORY_LOCATOR,
    *,
    remember_exact_count: int | None = None,
    apply_exact_percent: float | None = None,
) -> str:
    msg = (
        f"{source_locator}: synthetic fictitious board mandatory targets for generic "
        "paper distribution evaluation only."
    )
    if remember_exact_count is not None:
        msg += f" remember exact_count {remember_exact_count}."
    if apply_exact_percent is not None:
        msg += f" apply exact_percent {apply_exact_percent}."
    return msg


def mandatory_institution_policy_rule(
    *,
    value_json: dict,
    institution_id: str,
    priority: int = 20,
    source_locator: str | None = None,
) -> PolicyRule:
    meta: dict[str, object] = {}
    if source_locator:
        meta["mandatory_source_locator"] = source_locator
    return PolicyRule(
        scope_type=PolicyScopeType.INSTITUTION.value,
        scope_code=institution_id,
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json=value_json,
        priority=priority,
        active=True,
        metadata_json=meta,
    )


def mandatory_teacher_policy_rule(
    *,
    value_json: dict,
    teacher_id: str,
    priority: int = 30,
    source_locator: str | None = None,
) -> PolicyRule:
    meta: dict[str, object] = {}
    if source_locator:
        meta["mandatory_source_locator"] = source_locator
    return PolicyRule(
        scope_type=PolicyScopeType.TEACHER.value,
        scope_code=teacher_id,
        policy_key=PAPER_MANDATORY_POLICY_KEY,
        value_json=value_json,
        priority=priority,
        active=True,
        metadata_json=meta,
    )
