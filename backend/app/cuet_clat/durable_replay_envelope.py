from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.cuet_clat.constants import CLAT_PACK_CODE, CUET_PACK_CODE
from app.models.day13_replay import (
    D13_SYNTHETIC_TEST_ONLY_KEY,
    D13ReplayReservation,
)
from app.models.examination import ExamPack, ExamVersion

RESULT_SNAPSHOT_VERSION = "d13-replay-snapshot@v1"
MAX_IDEMPOTENCY_KEY_CHARS = 128
MAX_RESULT_JSON_BYTES = 8_192
FINGERPRINT_PREFIX = "d13-replay-fingerprint-v1"
BLUEPRINT_PREFIX = "d13-replay-blueprint-v1"


class D13ReservationState(StrEnum):
    RESERVED = "reserved"
    IN_PROGRESS = "in_progress"
    REPLAYED = "replayed"
    CONFLICT = "conflict"
    NOT_READY = "not_ready"
    CORRUPT = "corrupt"


class D13ReplayIssueCode(StrEnum):
    MISSING_TENANT = "missing_tenant"
    KEY_BLANK = "key_blank"
    KEY_OVERSIZE = "key_oversize"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    OWNER_MISMATCH = "owner_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    EXAM_VERSION_INVALID = "exam_version_invalid"
    EXAM_PACK_MISMATCH = "exam_pack_mismatch"
    RESULT_OVERSIZE = "result_oversize"
    PAYLOAD_INTEGRITY = "payload_integrity"
    PUBLISH_NOT_OWNER = "publish_not_owner"
    ALREADY_COMPLETE_CONFLICT = "already_complete_conflict"
    ROW_CORRUPT = "row_corrupt"
    DATABASE_LOCKED = "database_locked"


@dataclass(frozen=True, slots=True)
class D13ReplayScope:
    organization_id: str
    institution_id: str
    exam_pack_code: str
    exam_version_id: str
    academic_year: str


@dataclass(frozen=True, slots=True)
class D13ReplayEnvelopeOutcome:
    state: D13ReservationState
    reservation_id: str | None = None
    owner_token: str | None = None
    request_fingerprint: str | None = None
    payload_sha256: str | None = None
    result_payload: dict[str, object] | None = None
    issue_codes: tuple[D13ReplayIssueCode, ...] = field(default_factory=tuple)


def hash_idempotency_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def build_request_fingerprint(
    scope: D13ReplayScope,
    *,
    blueprint_snapshot: dict[str, object],
    source_snapshot_identity: str | None = None,
) -> str:
    payload = {
        "prefix": FINGERPRINT_PREFIX,
        "organization_id": scope.organization_id,
        "institution_id": scope.institution_id,
        "exam_pack_code": scope.exam_pack_code,
        "exam_version_id": scope.exam_version_id,
        "academic_year": scope.academic_year,
        "blueprint": _canonicalize_blueprint(blueprint_snapshot),
        "source_snapshot_identity": source_snapshot_identity or "",
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def payload_checksum(result_payload: dict[str, object]) -> str:
    blob = json.dumps(
        _canonicalize_blueprint(result_payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _canonicalize_blueprint(value: dict[str, object]) -> dict[str, object]:
    raw = json.loads(json.dumps(value, sort_keys=True, default=str))
    if not isinstance(raw, dict):
        return {}
    return {str(key): item for key, item in raw.items()}


def _validate_key(raw_key: str) -> D13ReplayIssueCode | None:
    stripped = raw_key.strip()
    if not stripped:
        return D13ReplayIssueCode.KEY_BLANK
    if len(stripped) > MAX_IDEMPOTENCY_KEY_CHARS:
        return D13ReplayIssueCode.KEY_OVERSIZE
    return None


def _validate_tenant(scope: D13ReplayScope) -> D13ReplayIssueCode | None:
    if not scope.organization_id.strip() or not scope.institution_id.strip():
        return D13ReplayIssueCode.MISSING_TENANT
    return None


def _validate_result_bounds(result_payload: dict[str, object]) -> D13ReplayIssueCode | None:
    blob = json.dumps(result_payload, sort_keys=True, default=str).encode("utf-8")
    if len(blob) > MAX_RESULT_JSON_BYTES:
        return D13ReplayIssueCode.RESULT_OVERSIZE
    return None


def verify_exam_version_scope(session: Session, scope: D13ReplayScope) -> D13ReplayIssueCode | None:
    version = session.get(ExamVersion, scope.exam_version_id)
    if version is None:
        return D13ReplayIssueCode.EXAM_VERSION_INVALID
    pack = session.get(ExamPack, version.exam_pack_id)
    if pack is None:
        return D13ReplayIssueCode.EXAM_VERSION_INVALID
    if pack.code != scope.exam_pack_code:
        return D13ReplayIssueCode.EXAM_PACK_MISMATCH
    if scope.exam_pack_code not in {CUET_PACK_CODE, CLAT_PACK_CODE}:
        return D13ReplayIssueCode.EXAM_PACK_MISMATCH
    return None


def _load_reservation(
    session: Session, scope: D13ReplayScope, key_hash: str
) -> D13ReplayReservation | None:
    return session.scalar(
        select(D13ReplayReservation).where(
            D13ReplayReservation.organization_id == scope.organization_id,
            D13ReplayReservation.institution_id == scope.institution_id,
            D13ReplayReservation.exam_pack_code == scope.exam_pack_code,
            D13ReplayReservation.exam_version_id == scope.exam_version_id,
            D13ReplayReservation.academic_year == scope.academic_year,
            D13ReplayReservation.idempotency_key_hash == key_hash,
        )
    )


def _row_integrity(row: D13ReplayReservation) -> D13ReplayIssueCode | None:
    if row.reservation_state == D13ReservationState.REPLAYED.value:
        if not row.payload_sha256 or row.result_json is None:
            return D13ReplayIssueCode.ROW_CORRUPT
        if row.payload_sha256 != payload_checksum(row.result_json):
            return D13ReplayIssueCode.PAYLOAD_INTEGRITY
        if row.result_snapshot_version != RESULT_SNAPSHOT_VERSION:
            return D13ReplayIssueCode.ROW_CORRUPT
    return None


def _outcome_from_row(
    row: D13ReplayReservation,
    *,
    expected_fingerprint: str,
) -> D13ReplayEnvelopeOutcome:
    corrupt = _row_integrity(row)
    if corrupt is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CORRUPT,
            reservation_id=row.id,
            request_fingerprint=row.request_fingerprint,
            issue_codes=(corrupt,),
        )
    if row.request_fingerprint != expected_fingerprint:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            reservation_id=row.id,
            issue_codes=(D13ReplayIssueCode.FINGERPRINT_MISMATCH,),
        )
    if row.reservation_state == D13ReservationState.REPLAYED.value:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.REPLAYED,
            reservation_id=row.id,
            request_fingerprint=row.request_fingerprint,
            payload_sha256=row.payload_sha256,
            result_payload=copy.deepcopy(row.result_json),
        )
    if row.reservation_state in {
        D13ReservationState.IN_PROGRESS.value,
        D13ReservationState.RESERVED.value,
    }:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.IN_PROGRESS,
            reservation_id=row.id,
            request_fingerprint=row.request_fingerprint,
        )
    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.NOT_READY,
        reservation_id=row.id,
        issue_codes=(D13ReplayIssueCode.ROW_CORRUPT,),
    )


def reserve_replay_slot(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    request_fingerprint: str,
) -> D13ReplayEnvelopeOutcome:
    tenant_issue = _validate_tenant(scope)
    if tenant_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(tenant_issue,),
        )
    key_issue = _validate_key(idempotency_key)
    if key_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(key_issue,),
        )
    exam_issue = verify_exam_version_scope(session, scope)
    if exam_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(exam_issue,),
        )

    key_hash = hash_idempotency_key(idempotency_key)
    existing = _load_reservation(session, scope, key_hash)
    if existing is not None:
        return _outcome_from_row(existing, expected_fingerprint=request_fingerprint)

    owner_token = uuid.uuid4().hex
    row = D13ReplayReservation(
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        exam_pack_code=scope.exam_pack_code,
        exam_version_id=scope.exam_version_id,
        academic_year=scope.academic_year,
        idempotency_key_hash=key_hash,
        request_fingerprint=request_fingerprint,
        reservation_state=D13ReservationState.RESERVED.value,
        owner_token=owner_token,
        metadata_json={D13_SYNTHETIC_TEST_ONLY_KEY: True},
    )
    try:
        session.add(row)
        session.flush()
    except (IntegrityError, OperationalError) as exc:
        session.rollback()
        if isinstance(exc, OperationalError) and "locked" in str(exc).lower():
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.NOT_READY,
                issue_codes=(D13ReplayIssueCode.DATABASE_LOCKED,),
            )
        raced = _load_reservation(session, scope, key_hash)
        if raced is None:
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.NOT_READY,
                issue_codes=(D13ReplayIssueCode.DATABASE_LOCKED,),
            )
        return _outcome_from_row(raced, expected_fingerprint=request_fingerprint)

    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.RESERVED,
        reservation_id=row.id,
        owner_token=owner_token,
        request_fingerprint=request_fingerprint,
    )


def publish_replay_result(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    owner_token: str,
    result_payload: dict[str, object],
) -> D13ReplayEnvelopeOutcome:
    key_issue = _validate_key(idempotency_key)
    if key_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(key_issue,),
        )
    size_issue = _validate_result_bounds(result_payload)
    if size_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(size_issue,),
        )

    safe_payload = copy.deepcopy(result_payload)
    safe_payload[D13_SYNTHETIC_TEST_ONLY_KEY] = True
    checksum = payload_checksum(safe_payload)

    key_hash = hash_idempotency_key(idempotency_key)
    row = _load_reservation(session, scope, key_hash)
    if row is None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(D13ReplayIssueCode.SCOPE_MISMATCH,),
        )
    if row.owner_token != owner_token:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            reservation_id=row.id,
            issue_codes=(D13ReplayIssueCode.PUBLISH_NOT_OWNER,),
        )
    if row.request_fingerprint != request_fingerprint:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            reservation_id=row.id,
            issue_codes=(D13ReplayIssueCode.FINGERPRINT_MISMATCH,),
        )
    if row.reservation_state == D13ReservationState.REPLAYED.value:
        if row.payload_sha256 == checksum:
            return _outcome_from_row(row, expected_fingerprint=request_fingerprint)
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            reservation_id=row.id,
            issue_codes=(D13ReplayIssueCode.ALREADY_COMPLETE_CONFLICT,),
        )
    if row.reservation_state not in {
        D13ReservationState.RESERVED.value,
        D13ReservationState.IN_PROGRESS.value,
    }:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            reservation_id=row.id,
            issue_codes=(D13ReplayIssueCode.ROW_CORRUPT,),
        )

    row.reservation_state = D13ReservationState.REPLAYED.value
    row.owner_token = None
    row.payload_sha256 = checksum
    row.result_snapshot_version = RESULT_SNAPSHOT_VERSION
    row.result_json = safe_payload
    session.flush()
    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.REPLAYED,
        reservation_id=row.id,
        request_fingerprint=request_fingerprint,
        payload_sha256=checksum,
        result_payload=copy.deepcopy(safe_payload),
    )


def read_replay_result(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    request_fingerprint: str,
) -> D13ReplayEnvelopeOutcome:
    key_issue = _validate_key(idempotency_key)
    if key_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(key_issue,),
        )
    key_hash = hash_idempotency_key(idempotency_key)
    row = _load_reservation(session, scope, key_hash)
    if row is None:
        return D13ReplayEnvelopeOutcome(state=D13ReservationState.NOT_READY)
    return _outcome_from_row(row, expected_fingerprint=request_fingerprint)


def abort_reservation(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    owner_token: str,
) -> D13ReplayEnvelopeOutcome:
    key_hash = hash_idempotency_key(idempotency_key)
    row = _load_reservation(session, scope, key_hash)
    if row is None:
        return D13ReplayEnvelopeOutcome(state=D13ReservationState.NOT_READY)
    if row.owner_token != owner_token:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.OWNER_MISMATCH,),
        )
    if row.request_fingerprint != request_fingerprint:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.FINGERPRINT_MISMATCH,),
        )
    if row.reservation_state == D13ReservationState.REPLAYED.value:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.ALREADY_COMPLETE_CONFLICT,),
        )
    session.delete(row)
    session.flush()
    return D13ReplayEnvelopeOutcome(state=D13ReservationState.NOT_READY)


def transition_to_in_progress(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    owner_token: str,
) -> D13ReplayEnvelopeOutcome:
    key_hash = hash_idempotency_key(idempotency_key)
    row = _load_reservation(session, scope, key_hash)
    if row is None or row.owner_token != owner_token:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.OWNER_MISMATCH,),
        )
    if row.request_fingerprint != request_fingerprint:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.FINGERPRINT_MISMATCH,),
        )
    row.reservation_state = D13ReservationState.IN_PROGRESS.value
    session.flush()
    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.IN_PROGRESS,
        reservation_id=row.id,
        owner_token=owner_token,
        request_fingerprint=request_fingerprint,
    )