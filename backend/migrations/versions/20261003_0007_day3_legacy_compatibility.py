"""repair compatibility for installations that already applied old 0006

Revision ID: 20261003_0007
Revises: 20261003_0006
Create Date: 2026-10-03
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20261003_0007"
down_revision = "20261003_0006"
branch_labels = None
depends_on = None

_REVIEW_STATES = {"extracted", "validated", "approved"}
_FINAL_STATES = {"active", "superseded"}
_IDENTITY_REPAIR_KEY = "_eduvijna_legacy_revision_identity"


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _repair_snapshot_collisions(rows: list[dict[str, Any]]) -> None:
    """Retain historical identities without deleting or redirecting references.

    Old 0006 could give two revisions identical bytes/snapshots but different
    identity hashes. The already-correct revision remains the canonical lookup
    target. Other rows retain every original snapshot field, with an additional
    explicitly migration-owned lineage field. Its real hash gives each retained
    historical row a distinct identity that still passes snapshot validation.
    This does not assert a change in the underlying official source metadata.
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    reserved: set[tuple[str, str, str]] = set()
    for row in rows:
        metadata = _json_object(row["metadata_json"])
        snapshot = metadata.get("source_snapshot")
        if not isinstance(snapshot, dict):
            raise RuntimeError(
                "Source revision is missing source_snapshot metadata: " + str(row["id"])
            )
        actual_checksum = _sha256(_canonical_json_bytes(snapshot))
        identity = (str(row["source_id"]), str(row["checksum"]), actual_checksum)
        groups.setdefault(identity, []).append(row)
        reserved.add(identity)

    for identity, group in groups.items():
        if len(group) < 2:
            continue
        canonical = next(
            (row for row in group if str(row["source_snapshot_checksum"]) == identity[2]),
            group[0],
        )
        for row in group:
            if row is canonical:
                continue
            metadata = _json_object(row["metadata_json"])
            snapshot = dict(metadata["source_snapshot"])
            key = _IDENTITY_REPAIR_KEY
            # A pre-existing field must never be overwritten, even if it uses
            # our reserved name. Check all planned final identities as well.
            while True:
                if key not in snapshot:
                    repaired_snapshot = {
                        **snapshot,
                        key: {
                            "migration_revision": revision,
                            "revision_id": str(row["id"]),
                            "canonical_revision_id": str(canonical["id"]),
                            "original_source_snapshot_checksum": str(
                                row["source_snapshot_checksum"]
                            ),
                            "canonical_source_snapshot_checksum": identity[2],
                        },
                    }
                    checksum = _sha256(_canonical_json_bytes(repaired_snapshot))
                    repaired_identity = (identity[0], identity[1], checksum)
                    if repaired_identity not in reserved:
                        break
                key += "_"
            reserved.add(repaired_identity)
            row["metadata_json"] = {**metadata, "source_snapshot": repaired_snapshot}


def _temporary_snapshot_checksums(
    rows: list[dict[str, Any]], updates: list[dict[str, Any]]
) -> dict[str, str]:
    """Stage identity rewrites safely even when old hashes occupy new keys."""
    by_id = {str(row["id"]): row for row in rows}
    occupied = {
        (str(row["source_id"]), str(row["checksum"]), str(row["source_snapshot_checksum"]))
        for row in rows
    }
    occupied.update(
        (
            str(by_id[item["id"]]["source_id"]),
            str(by_id[item["id"]]["checksum"]),
            str(item["source_snapshot_checksum"]),
        )
        for item in updates
    )
    result: dict[str, str] = {}
    for item in updates:
        row = by_id[item["id"]]
        attempt = 0
        while True:
            checksum = _sha256(
                _canonical_json_bytes([revision, "temporary-identity", item["id"], attempt])
            )
            identity = (str(row["source_id"]), str(row["checksum"]), checksum)
            if identity not in occupied:
                break
            attempt += 1
        occupied.add(identity)
        result[item["id"]] = checksum
    return result


def upgrade() -> None:
    bind = op.get_bind()
    rows = [
        dict(row)
        for row in bind.execute(
            sa.text(
                """
                SELECT
                    id,
                    source_id,
                    checksum,
                    source_snapshot_checksum,
                    ingestion_method,
                    extraction_status,
                    status,
                    metadata_json
                FROM source_revisions
                ORDER BY source_id, revision_number, id
                """
            )
        ).mappings()
    ]
    _repair_snapshot_collisions(rows)
    updates: list[dict[str, Any]] = []

    invalid_manual: list[str] = []
    for row in rows:
        revision_id = str(row["id"])
        checksum = str(row["checksum"])
        metadata = _json_object(row["metadata_json"])
        snapshot = metadata.get("source_snapshot")
        if not isinstance(snapshot, dict):
            raise RuntimeError(
                "Source revision is missing source_snapshot metadata: " + revision_id
            )

        actual_snapshot_checksum = _sha256(_canonical_json_bytes(snapshot))
        if str(row["source_snapshot_checksum"]) == actual_snapshot_checksum:
            continue

        ingestion_method = str(row["ingestion_method"])
        extraction_status = str(row["extraction_status"])
        status = str(row["status"])
        new_status = status
        new_extraction_status = extraction_status
        extracted_checksum: str | None = None
        validated_checksum: str | None = None
        clear_extracted = False
        clear_approval = False

        if ingestion_method == "manual":
            manual_metadata = metadata.get("manual_metadata")
            if not isinstance(manual_metadata, dict):
                invalid_manual.append(revision_id)
                continue
            actual_checksum = _sha256(_canonical_json_bytes(manual_metadata))
            if actual_checksum != checksum:
                invalid_manual.append(revision_id)
                continue

            if extraction_status == "succeeded":
                extracted_checksum = checksum
            if status in {"validated", "approved"}:
                new_status = "extracted"
                new_extraction_status = "succeeded"
                clear_approval = True
            elif status in _FINAL_STATES:
                validated_checksum = checksum
        else:
            if status in _REVIEW_STATES:
                new_status = "staged"
                new_extraction_status = "pending"
                clear_extracted = True
                clear_approval = True
            elif status in _FINAL_STATES:
                if extraction_status == "succeeded":
                    extracted_checksum = checksum
                validated_checksum = checksum

        updates.append(
            {
                "id": revision_id,
                "source_snapshot_checksum": actual_snapshot_checksum,
                "metadata_json": metadata,
                "extracted_checksum": extracted_checksum,
                "validated_checksum": validated_checksum,
                "status": new_status,
                "extraction_status": new_extraction_status,
                "clear_extracted": clear_extracted,
                "clear_approval": clear_approval,
            }
        )

    if invalid_manual:
        raise RuntimeError(
            "Existing manual source revisions have unverifiable metadata/checksum: "
            + ",".join(invalid_manual)
        )

    # Preflight finishes before any writes. The migration transaction makes the
    # temporary identity stage and lifecycle repair atomic on both databases.
    for revision_id, checksum in _temporary_snapshot_checksums(rows, updates).items():
        bind.execute(
            sa.text(
                "UPDATE source_revisions SET source_snapshot_checksum = :checksum "
                "WHERE id = :id"
            ),
            {"id": revision_id, "checksum": checksum},
        )
    for item in updates:
        bind.execute(
            sa.text(
                """
                UPDATE source_revisions
                SET source_snapshot_checksum = :source_snapshot_checksum,
                    metadata_json = :metadata_json,
                    extracted_checksum = :extracted_checksum,
                    validated_checksum = :validated_checksum,
                    approval_fingerprint = NULL,
                    status = :status,
                    extraction_status = :extraction_status,
                    extracted_text = CASE
                        WHEN :clear_extracted THEN NULL
                        ELSE extracted_text
                    END,
                    extraction_metadata_json = CASE
                        WHEN :clear_extracted THEN '{}'
                        ELSE extraction_metadata_json
                    END,
                    approved_by = CASE
                        WHEN :clear_approval THEN NULL
                        ELSE approved_by
                    END,
                    approved_at = CASE
                        WHEN :clear_approval THEN NULL
                        ELSE approved_at
                    END
                WHERE id = :id
                """
            ).bindparams(sa.bindparam("metadata_json", type_=sa.JSON())),
            item,
        )


def downgrade() -> None:
    # Data repair is intentionally retained. Schema ownership remains with 0006.
    pass
