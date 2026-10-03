"""repair compatibility for installations that already applied old 0006

Revision ID: 20261003_0007
Revises: 20261003_0006
Create Date: 2026-10-03
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from alembic import op
import sqlalchemy as sa

revision = "20261003_0007"
down_revision = "20261003_0006"
branch_labels = None
depends_on = None

_REVIEW_STATES = {"extracted", "validated", "approved"}
_FINAL_STATES = {"active", "superseded"}


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


def upgrade() -> None:
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                """
                SELECT
                    id,
                    checksum,
                    source_snapshot_checksum,
                    ingestion_method,
                    extraction_status,
                    status,
                    metadata_json
                FROM source_revisions
                ORDER BY source_id, revision_number
                """
            )
        ).mappings()
    )

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

        bind.execute(
            sa.text(
                """
                UPDATE source_revisions
                SET source_snapshot_checksum = :source_snapshot_checksum,
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
            ),
            {
                "id": revision_id,
                "source_snapshot_checksum": actual_snapshot_checksum,
                "extracted_checksum": extracted_checksum,
                "validated_checksum": validated_checksum,
                "status": new_status,
                "extraction_status": new_extraction_status,
                "clear_extracted": clear_extracted,
                "clear_approval": clear_approval,
            },
        )

    if invalid_manual:
        raise RuntimeError(
            "Existing manual source revisions have unverifiable metadata/checksum: "
            + ",".join(invalid_manual)
        )


def downgrade() -> None:
    # Data repair is intentionally retained. Schema ownership remains with 0006.
    pass
