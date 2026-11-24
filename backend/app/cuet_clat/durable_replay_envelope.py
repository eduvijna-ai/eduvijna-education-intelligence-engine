from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.cuet_clat.constants import (
    CLAT_PACK_CODE,
    CUET_PACK_CODE,
    VERSION_CLAT_2027,
    VERSION_SYNTHETIC_DEMO,
)
from app.models.day13_replay import (
    D13_SYNTHETIC_TEST_ONLY_KEY,
    D13ReplayReservation,
)
from app.models.examination import ExamPack, ExamVersion

RESULT_SNAPSHOT_VERSION = "d13-replay-snapshot@v2"
MAX_IDEMPOTENCY_KEY_CHARS = 128
MAX_RESULT_JSON_BYTES = 8_192
FINGERPRINT_PREFIX = "d13-replay-fingerprint-v2"
BLUEPRINT_PREFIX = "d13-replay-blueprint-v1"
SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")
FORBIDDEN_RESULT_KEYS = frozenset(
    {
        "question_text",
        "questions",
        "passage",
        "passages",
        "options",
        "answer",
        "answer_key",
        "learner",
        "pii",
        "source_bytes",
        "official_claim",
    }
)


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
    FINGERPRINT_INVALID = "fingerprint_invalid"
    FINGERPRINT_ASSERTED_MISMATCH = "fingerprint_asserted_mismatch"
    BLUEPRINT_INVALID = "blueprint_invalid"
    OWNER_MISMATCH = "owner_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    EXAM_VERSION_INVALID = "exam_version_invalid"
    EXAM_PACK_MISMATCH = "exam_pack_mismatch"
    EXAM_YEAR_MISMATCH = "exam_year_mismatch"
    RESULT_OVERSIZE = "result_oversize"
    RESULT_SCHEMA_VIOLATION = "result_schema_violation"
    PAYLOAD_INTEGRITY = "payload_integrity"
    PUBLISH_NOT_OWNER = "publish_not_owner"
    ALREADY_COMPLETE_CONFLICT = "already_complete_conflict"
    ROW_CORRUPT = "row_corrupt"
    DATABASE_LOCKED = "database_locked"
    CAS_TRANSITION_FAILED = "cas_transition_failed"


class D13OpaqueReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    synthetic_demo_checksum: str = Field(min_length=1, max_length=128)
    opaque_plan_ref: str = Field(min_length=1, max_length=256)
    plan_checksum_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


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
    commit_required: bool = False


def hash_idempotency_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _is_valid_sha256_hex(value: str) -> bool:
    return bool(SHA256_HEX.fullmatch(value))


def _strict_json_dumps(payload: dict[str, Any]) -> bytes:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return text.encode("utf-8")


def _normalize_blueprint_snapshot(blueprint_snapshot: dict[str, object]) -> dict[str, object]:
    if not isinstance(blueprint_snapshot, dict):
        msg = "blueprint must be object"
        raise TypeError(msg)
    normalized: dict[str, object] = {}
    for key, value in blueprint_snapshot.items():
        if not isinstance(key, str):
            raise TypeError("blueprint keys must be strings")
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized[key] = value
        else:
            raise TypeError("blueprint values must be JSON primitives")
    return normalized


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
        "blueprint": _normalize_blueprint_snapshot(blueprint_snapshot),
        "source_snapshot_identity": source_snapshot_identity or "",
    }
    return hashlib.sha256(_strict_json_dumps(payload)).hexdigest()


def derive_request_fingerprint(
    scope: D13ReplayScope,
    *,
    blueprint_snapshot: dict[str, object],
    source_snapshot_identity: str | None = None,
    asserted_fingerprint: str | None = None,
) -> tuple[str | None, D13ReplayIssueCode | None]:
    try:
        normalized = _normalize_blueprint_snapshot(blueprint_snapshot)
    except TypeError:
        return None, D13ReplayIssueCode.BLUEPRINT_INVALID
    computed = build_request_fingerprint(
        scope,
        blueprint_snapshot=normalized,
        source_snapshot_identity=source_snapshot_identity,
    )
    if asserted_fingerprint is not None:
        if not _is_valid_sha256_hex(asserted_fingerprint):
            return None, D13ReplayIssueCode.FINGERPRINT_INVALID
        if asserted_fingerprint != computed:
            return None, D13ReplayIssueCode.FINGERPRINT_ASSERTED_MISMATCH
    return computed, None


def payload_checksum(result_payload: dict[str, object]) -> str:
    return hashlib.sha256(_strict_json_dumps(result_payload)).hexdigest()


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


def verify_exam_version_scope(session: Session, scope: D13ReplayScope) -> D13ReplayIssueCode | None:
    version = session.get(ExamVersion, scope.exam_version_id)
    if version is None:
        return D13ReplayIssueCode.EXAM_VERSION_INVALID
    pack = session.get(ExamPack, version.exam_pack_id)
    if pack is None:
        return D13ReplayIssueCode.EXAM_VERSION_INVALID
    if pack.code != scope.exam_pack_code:
        return D13ReplayIssueCode.EXAM_PACK_MISMATCH
    if scope.academic_year != version.academic_year:
        return D13ReplayIssueCode.EXAM_YEAR_MISMATCH
    if pack.code == CUET_PACK_CODE:
        if version.version_code != VERSION_SYNTHETIC_DEMO or scope.academic_year != "2026":
            return D13ReplayIssueCode.EXAM_VERSION_INVALID
    elif pack.code == CLAT_PACK_CODE:
        if version.version_code != VERSION_CLAT_2027 or scope.academic_year != "2027":
            return D13ReplayIssueCode.EXAM_VERSION_INVALID
    else:
        return D13ReplayIssueCode.EXAM_PACK_MISMATCH
    return None


def _validate_and_seal_result(
    result_payload: dict[str, object],
) -> tuple[dict[str, object] | None, str | None, D13ReplayIssueCode | None]:
    for forbidden in FORBIDDEN_RESULT_KEYS:
        if forbidden in result_payload:
            return None, None, D13ReplayIssueCode.RESULT_SCHEMA_VIOLATION
    try:
        model = D13OpaqueReplayResult.model_validate(result_payload)
    except ValidationError:
        return None, None, D13ReplayIssueCode.RESULT_SCHEMA_VIOLATION
    sealed = model.model_dump()
    sealed[D13_SYNTHETIC_TEST_ONLY_KEY] = True
    try:
        blob = _strict_json_dumps(sealed)
    except (TypeError, ValueError):
        return None, None, D13ReplayIssueCode.RESULT_SCHEMA_VIOLATION
    if len(blob) > MAX_RESULT_JSON_BYTES:
        return None, None, D13ReplayIssueCode.RESULT_OVERSIZE
    checksum = hashlib.sha256(blob).hexdigest()
    return sealed, checksum, None


def _execute_rowcount(session: Session, statement: Any) -> int:
    result = session.execute(statement)
    rowcount = getattr(result, "rowcount", 0)
    return int(rowcount) if rowcount is not None else 0


def _scope_filters(scope: D13ReplayScope, key_hash: str) -> list[Any]:
    return [
        D13ReplayReservation.organization_id == scope.organization_id,
        D13ReplayReservation.institution_id == scope.institution_id,
        D13ReplayReservation.exam_pack_code == scope.exam_pack_code,
        D13ReplayReservation.exam_version_id == scope.exam_version_id,
        D13ReplayReservation.academic_year == scope.academic_year,
        D13ReplayReservation.idempotency_key_hash == key_hash,
    ]


def _load_reservation(
    session: Session, scope: D13ReplayScope, key_hash: str
) -> D13ReplayReservation | None:
    return session.scalar(select(D13ReplayReservation).where(*_scope_filters(scope, key_hash)))


def _validate_result_schema_dict(result: dict[str, Any]) -> bool:
    try:
        D13OpaqueReplayResult.model_validate(
            {k: v for k, v in result.items() if k != D13_SYNTHETIC_TEST_ONLY_KEY}
        )
    except ValidationError:
        return False
    if result.get(D13_SYNTHETIC_TEST_ONLY_KEY) is not True:
        return False
    for forbidden in FORBIDDEN_RESULT_KEYS:
        if forbidden in result:
            return False
    return True


def _row_integrity(row: D13ReplayReservation) -> D13ReplayIssueCode | None:
    if row.metadata_json.get(D13_SYNTHETIC_TEST_ONLY_KEY) is not True:
        return D13ReplayIssueCode.ROW_CORRUPT
    if not _is_valid_sha256_hex(row.request_fingerprint):
        return D13ReplayIssueCode.ROW_CORRUPT
    state = row.reservation_state
    if state in {D13ReservationState.RESERVED.value, D13ReservationState.IN_PROGRESS.value}:
        if not row.owner_token:
            return D13ReplayIssueCode.ROW_CORRUPT
        if row.result_json is not None or row.payload_sha256 or row.result_snapshot_version:
            return D13ReplayIssueCode.ROW_CORRUPT
        return None
    if state == D13ReservationState.REPLAYED.value:
        if row.owner_token is not None:
            return D13ReplayIssueCode.ROW_CORRUPT
        if not row.payload_sha256 or row.result_json is None or not row.result_snapshot_version:
            return D13ReplayIssueCode.ROW_CORRUPT
        if row.result_snapshot_version != RESULT_SNAPSHOT_VERSION:
            return D13ReplayIssueCode.ROW_CORRUPT
        if not _validate_result_schema_dict(row.result_json):
            return D13ReplayIssueCode.ROW_CORRUPT
        if row.payload_sha256 != payload_checksum(row.result_json):
            return D13ReplayIssueCode.PAYLOAD_INTEGRITY
        return None
    return D13ReplayIssueCode.ROW_CORRUPT


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
        state=D13ReservationState.CORRUPT,
        reservation_id=row.id,
        issue_codes=(D13ReplayIssueCode.ROW_CORRUPT,),
    )


def reserve_replay_slot(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    blueprint_snapshot: dict[str, object],
    source_snapshot_identity: str | None = None,
    asserted_fingerprint: str | None = None,
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
    fingerprint, fp_issue = derive_request_fingerprint(
        scope,
        blueprint_snapshot=blueprint_snapshot,
        source_snapshot_identity=source_snapshot_identity,
        asserted_fingerprint=asserted_fingerprint,
    )
    if fp_issue is not None or fingerprint is None:
        issue = fp_issue or D13ReplayIssueCode.FINGERPRINT_INVALID
        state = (
            D13ReservationState.CONFLICT
            if issue is D13ReplayIssueCode.FINGERPRINT_ASSERTED_MISMATCH
            else D13ReservationState.NOT_READY
        )
        return D13ReplayEnvelopeOutcome(state=state, issue_codes=(issue,))

    key_hash = hash_idempotency_key(idempotency_key)
    existing = _load_reservation(session, scope, key_hash)
    if existing is not None:
        return _outcome_from_row(existing, expected_fingerprint=fingerprint)

    owner_token = uuid.uuid4().hex
    row = D13ReplayReservation(
        organization_id=scope.organization_id,
        institution_id=scope.institution_id,
        exam_pack_code=scope.exam_pack_code,
        exam_version_id=scope.exam_version_id,
        academic_year=scope.academic_year,
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
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
        return _outcome_from_row(raced, expected_fingerprint=fingerprint)

    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.RESERVED,
        reservation_id=row.id,
        owner_token=owner_token,
        request_fingerprint=fingerprint,
        commit_required=True,
    )


def _fingerprint_for_mutation(
    scope: D13ReplayScope,
    *,
    blueprint_snapshot: dict[str, object],
    source_snapshot_identity: str | None = None,
    asserted_fingerprint: str | None = None,
) -> tuple[str | None, D13ReplayEnvelopeOutcome | None]:
    fingerprint, fp_issue = derive_request_fingerprint(
        scope,
        blueprint_snapshot=blueprint_snapshot,
        source_snapshot_identity=source_snapshot_identity,
        asserted_fingerprint=asserted_fingerprint,
    )
    if fp_issue is not None or fingerprint is None:
        issue = fp_issue or D13ReplayIssueCode.FINGERPRINT_INVALID
        return None, D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(issue,),
        )
    return fingerprint, None


def publish_replay_result(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    blueprint_snapshot: dict[str, object],
    owner_token: str,
    result_payload: dict[str, object],
    source_snapshot_identity: str | None = None,
    asserted_fingerprint: str | None = None,
) -> D13ReplayEnvelopeOutcome:
    key_issue = _validate_key(idempotency_key)
    if key_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(key_issue,),
        )
    fingerprint, bad = _fingerprint_for_mutation(
        scope,
        blueprint_snapshot=blueprint_snapshot,
        source_snapshot_identity=source_snapshot_identity,
        asserted_fingerprint=asserted_fingerprint,
    )
    if bad is not None:
        return bad
    assert fingerprint is not None

    sealed, checksum, result_issue = _validate_and_seal_result(result_payload)
    if result_issue is not None or sealed is None or checksum is None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(result_issue or D13ReplayIssueCode.RESULT_SCHEMA_VIOLATION,),
        )

    key_hash = hash_idempotency_key(idempotency_key)
    try:
        affected = _execute_rowcount(
            session,
            update(D13ReplayReservation)
            .where(
                *(
                    _scope_filters(scope, key_hash)
                    + [
                        D13ReplayReservation.owner_token == owner_token,
                        D13ReplayReservation.request_fingerprint == fingerprint,
                        D13ReplayReservation.reservation_state.in_(
                            [
                                D13ReservationState.RESERVED.value,
                                D13ReservationState.IN_PROGRESS.value,
                            ]
                        ),
                    ]
                )
            )
            .values(
                reservation_state=D13ReservationState.REPLAYED.value,
                owner_token=None,
                payload_sha256=checksum,
                result_snapshot_version=RESULT_SNAPSHOT_VERSION,
                result_json=sealed,
            ),
        )
        if affected == 1:
            session.flush()
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.REPLAYED,
                request_fingerprint=fingerprint,
                payload_sha256=checksum,
                result_payload=copy.deepcopy(sealed),
                commit_required=True,
            )
    except (IntegrityError, OperationalError) as exc:
        session.rollback()
        if isinstance(exc, OperationalError) and "locked" in str(exc).lower():
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.NOT_READY,
                issue_codes=(D13ReplayIssueCode.DATABASE_LOCKED,),
            )
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(D13ReplayIssueCode.CAS_TRANSITION_FAILED,),
        )

    existing = _load_reservation(session, scope, key_hash)
    if existing is None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(D13ReplayIssueCode.SCOPE_MISMATCH,),
        )
    prior = _row_integrity(existing)
    if prior is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CORRUPT,
            reservation_id=existing.id,
            issue_codes=(prior,),
        )
    if existing.reservation_state == D13ReservationState.REPLAYED.value:
        if existing.payload_sha256 == checksum:
            return _outcome_from_row(existing, expected_fingerprint=fingerprint)
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            reservation_id=existing.id,
            issue_codes=(D13ReplayIssueCode.ALREADY_COMPLETE_CONFLICT,),
        )
    if existing.owner_token != owner_token:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            reservation_id=existing.id,
            issue_codes=(D13ReplayIssueCode.PUBLISH_NOT_OWNER,),
        )
    if existing.request_fingerprint != fingerprint:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            reservation_id=existing.id,
            issue_codes=(D13ReplayIssueCode.FINGERPRINT_MISMATCH,),
        )
    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.CONFLICT,
        reservation_id=existing.id,
        issue_codes=(D13ReplayIssueCode.CAS_TRANSITION_FAILED,),
    )


def read_replay_result(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    blueprint_snapshot: dict[str, object],
    source_snapshot_identity: str | None = None,
    asserted_fingerprint: str | None = None,
) -> D13ReplayEnvelopeOutcome:
    key_issue = _validate_key(idempotency_key)
    if key_issue is not None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(key_issue,),
        )
    fingerprint, bad = _fingerprint_for_mutation(
        scope,
        blueprint_snapshot=blueprint_snapshot,
        source_snapshot_identity=source_snapshot_identity,
        asserted_fingerprint=asserted_fingerprint,
    )
    if bad is not None:
        return bad
    assert fingerprint is not None
    key_hash = hash_idempotency_key(idempotency_key)
    row = _load_reservation(session, scope, key_hash)
    if row is None:
        return D13ReplayEnvelopeOutcome(state=D13ReservationState.NOT_READY)
    return _outcome_from_row(row, expected_fingerprint=fingerprint)


def abort_reservation(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    blueprint_snapshot: dict[str, object],
    owner_token: str,
    source_snapshot_identity: str | None = None,
    asserted_fingerprint: str | None = None,
) -> D13ReplayEnvelopeOutcome:
    fingerprint, bad = _fingerprint_for_mutation(
        scope,
        blueprint_snapshot=blueprint_snapshot,
        source_snapshot_identity=source_snapshot_identity,
        asserted_fingerprint=asserted_fingerprint,
    )
    if bad is not None:
        return bad
    assert fingerprint is not None
    key_hash = hash_idempotency_key(idempotency_key)
    try:
        removed = _execute_rowcount(
            session,
            delete(D13ReplayReservation).where(
                *(
                    _scope_filters(scope, key_hash)
                    + [
                        D13ReplayReservation.owner_token == owner_token,
                        D13ReplayReservation.request_fingerprint == fingerprint,
                        D13ReplayReservation.reservation_state.in_(
                            [
                                D13ReservationState.RESERVED.value,
                                D13ReservationState.IN_PROGRESS.value,
                            ]
                        ),
                    ]
                )
            ),
        )
        if removed == 1:
            session.flush()
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.NOT_READY,
                commit_required=True,
            )
    except OperationalError as exc:
        session.rollback()
        if "locked" in str(exc).lower():
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.NOT_READY,
                issue_codes=(D13ReplayIssueCode.DATABASE_LOCKED,),
            )

    existing = _load_reservation(session, scope, key_hash)
    if existing is None:
        return D13ReplayEnvelopeOutcome(state=D13ReservationState.NOT_READY)
    if existing.reservation_state == D13ReservationState.REPLAYED.value:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.ALREADY_COMPLETE_CONFLICT,),
        )
    if existing.owner_token != owner_token:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.OWNER_MISMATCH,),
        )
    if existing.request_fingerprint != fingerprint:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.FINGERPRINT_MISMATCH,),
        )
    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.CONFLICT,
        issue_codes=(D13ReplayIssueCode.CAS_TRANSITION_FAILED,),
    )


def transition_to_in_progress(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    blueprint_snapshot: dict[str, object],
    owner_token: str,
    source_snapshot_identity: str | None = None,
    asserted_fingerprint: str | None = None,
) -> D13ReplayEnvelopeOutcome:
    fingerprint, bad = _fingerprint_for_mutation(
        scope,
        blueprint_snapshot=blueprint_snapshot,
        source_snapshot_identity=source_snapshot_identity,
        asserted_fingerprint=asserted_fingerprint,
    )
    if bad is not None:
        return bad
    assert fingerprint is not None
    key_hash = hash_idempotency_key(idempotency_key)
    try:
        affected = _execute_rowcount(
            session,
            update(D13ReplayReservation)
            .where(
                *(
                    _scope_filters(scope, key_hash)
                    + [
                        D13ReplayReservation.owner_token == owner_token,
                        D13ReplayReservation.request_fingerprint == fingerprint,
                        D13ReplayReservation.reservation_state
                        == D13ReservationState.RESERVED.value,
                    ]
                )
            )
            .values(reservation_state=D13ReservationState.IN_PROGRESS.value),
        )
        if affected == 1:
            session.flush()
            row = _load_reservation(session, scope, key_hash)
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.IN_PROGRESS,
                reservation_id=row.id if row else None,
                owner_token=owner_token,
                request_fingerprint=fingerprint,
                commit_required=True,
            )
    except OperationalError as exc:
        session.rollback()
        if "locked" in str(exc).lower():
            return D13ReplayEnvelopeOutcome(
                state=D13ReservationState.NOT_READY,
                issue_codes=(D13ReplayIssueCode.DATABASE_LOCKED,),
            )

    existing = _load_reservation(session, scope, key_hash)
    if existing is None:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.NOT_READY,
            issue_codes=(D13ReplayIssueCode.SCOPE_MISMATCH,),
        )
    if existing.owner_token != owner_token:
        return D13ReplayEnvelopeOutcome(
            state=D13ReservationState.CONFLICT,
            issue_codes=(D13ReplayIssueCode.OWNER_MISMATCH,),
        )
    return D13ReplayEnvelopeOutcome(
        state=D13ReservationState.CONFLICT,
        issue_codes=(D13ReplayIssueCode.CAS_TRANSITION_FAILED,),
    )


def confirmed_read_after_commit(
    session: Session,
    scope: D13ReplayScope,
    *,
    idempotency_key: str,
    blueprint_snapshot: dict[str, object],
    source_snapshot_identity: str | None = None,
) -> D13ReplayEnvelopeOutcome:
    """Read durable row after caller committed reserve/publish."""
    session.expire_all()
    return read_replay_result(
        session,
        scope,
        idempotency_key=idempotency_key,
        blueprint_snapshot=blueprint_snapshot,
        source_snapshot_identity=source_snapshot_identity,
    )