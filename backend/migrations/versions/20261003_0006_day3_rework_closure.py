"""close audited Day 3 Source Intelligence gaps

Revision ID: 20261003_0006
Revises: 20261002_0005
Create Date: 2026-10-03
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from alembic import op
import sqlalchemy as sa

revision = "20261003_0006"
down_revision = "20261002_0005"
branch_labels = None
depends_on = None

_OWNERSHIP_REPAIR_KEY = "_day3_ownership_repair"
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


def _validate_legacy_ownership(bind: Any) -> dict[str, dict[str, str | None]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT id, source_type, metadata_json
            FROM sources
            WHERE source_type IN ('institution_content', 'teacher_content')
            ORDER BY id
            """
        )
    ).mappings()

    mappings: dict[str, dict[str, str | None]] = {}
    missing: list[str] = []
    invalid: list[str] = []

    for row in rows:
        source_id = str(row["id"])
        source_type = str(row["source_type"])
        metadata = _json_object(row["metadata_json"])
        repair = metadata.get(_OWNERSHIP_REPAIR_KEY)
        if not isinstance(repair, dict):
            missing.append(source_id)
            continue

        organization_id = repair.get("organization_id")
        institution_id = repair.get("institution_id")
        teacher_id = repair.get("teacher_id")
        if not isinstance(organization_id, str) or not isinstance(institution_id, str):
            invalid.append(source_id)
            continue
        if source_type == "institution_content" and teacher_id is not None:
            invalid.append(source_id)
            continue
        if source_type == "teacher_content" and not isinstance(teacher_id, str):
            invalid.append(source_id)
            continue

        institution = bind.execute(
            sa.text(
                """
                SELECT organization_id
                FROM institutions
                WHERE id = :institution_id
                """
            ),
            {"institution_id": institution_id},
        ).mappings().first()
        if (
            institution is None
            or str(institution["organization_id"]) != organization_id
        ):
            invalid.append(source_id)
            continue

        organization_exists = bind.execute(
            sa.text("SELECT 1 FROM organizations WHERE id = :id"),
            {"id": organization_id},
        ).first()
        if organization_exists is None:
            invalid.append(source_id)
            continue

        if teacher_id is not None:
            teacher = bind.execute(
                sa.text(
                    """
                    SELECT institution_id
                    FROM teachers
                    WHERE id = :teacher_id
                    """
                ),
                {"teacher_id": teacher_id},
            ).mappings().first()
            if teacher is None or str(teacher["institution_id"]) != institution_id:
                invalid.append(source_id)
                continue

        mappings[source_id] = {
            "organization_id": organization_id,
            "institution_id": institution_id,
            "teacher_id": teacher_id if isinstance(teacher_id, str) else None,
        }

    if missing or invalid:
        details: list[str] = []
        if missing:
            details.append("missing ownership repair: " + ",".join(missing))
        if invalid:
            details.append("invalid ownership repair: " + ",".join(invalid))
        raise RuntimeError(
            "Legacy tenant-owned Day-3 sources require explicit ownership repair "
            "before migration. Run python -m app.source_legacy_repair inspect "
            "and python -m app.source_legacy_repair apply --mapping <file>. "
            + "; ".join(details)
        )

    return mappings


def _legacy_revision_updates(bind: Any) -> list[dict[str, Any]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                checksum,
                ingestion_method,
                extraction_status,
                status,
                metadata_json
            FROM source_revisions
            ORDER BY source_id, revision_number
            """
        )
    ).mappings()

    updates: list[dict[str, Any]] = []
    invalid_manual: list[str] = []

    for row in rows:
        revision_id = str(row["id"])
        checksum = str(row["checksum"])
        ingestion_method = str(row["ingestion_method"])
        extraction_status = str(row["extraction_status"])
        status = str(row["status"])
        metadata = _json_object(row["metadata_json"])
        snapshot = metadata.get("source_snapshot")
        if not isinstance(snapshot, dict):
            raise RuntimeError(
                "Legacy source revision is missing source_snapshot metadata: "
                + revision_id
            )

        snapshot_checksum = _sha256(_canonical_json_bytes(snapshot))
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
            if status in _REVIEW_STATES:
                new_status = "extracted"
                new_extraction_status = "succeeded"
                validated_checksum = None
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
                "source_snapshot_checksum": snapshot_checksum,
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
            "Legacy manual source revisions have unverifiable metadata/checksum: "
            + ",".join(invalid_manual)
        )

    return updates


def upgrade() -> None:
    bind = op.get_bind()

    ownership_mappings = _validate_legacy_ownership(bind)
    revision_updates = _legacy_revision_updates(bind)

    with op.batch_alter_table("sources") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("institution_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("teacher_id", sa.String(36), nullable=True))

    for source_id, mapping in ownership_mappings.items():
        bind.execute(
            sa.text(
                """
                UPDATE sources
                SET organization_id = :organization_id,
                    institution_id = :institution_id,
                    teacher_id = :teacher_id
                WHERE id = :source_id
                """
            ),
            {**mapping, "source_id": source_id},
        )

    with op.batch_alter_table("sources") as batch:
        batch.create_foreign_key(
            "fk_sources_organization_id_organizations",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_sources_institution_id_institutions",
            "institutions",
            ["institution_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_sources_teacher_id_teachers",
            "teachers",
            ["teacher_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_source_institution_same_organization",
            "institutions",
            ["institution_id", "organization_id"],
            ["id", "organization_id"],
        )
        batch.create_foreign_key(
            "fk_source_teacher_same_institution",
            "teachers",
            ["teacher_id", "institution_id"],
            ["id", "institution_id"],
        )
        batch.create_check_constraint(
            "ck_source_institution_requires_organization",
            "institution_id IS NULL OR organization_id IS NOT NULL",
        )
        batch.create_check_constraint(
            "ck_source_teacher_requires_institution",
            "teacher_id IS NULL OR institution_id IS NOT NULL",
        )
        batch.create_check_constraint(
            "ck_source_ownership_shape",
            "("
            "source_type = 'institution_content' "
            "AND organization_id IS NOT NULL "
            "AND institution_id IS NOT NULL "
            "AND teacher_id IS NULL"
            ") OR ("
            "source_type = 'teacher_content' "
            "AND organization_id IS NOT NULL "
            "AND institution_id IS NOT NULL "
            "AND teacher_id IS NOT NULL"
            ") OR ("
            "source_type NOT IN ('institution_content','teacher_content') "
            "AND organization_id IS NULL "
            "AND institution_id IS NULL "
            "AND teacher_id IS NULL"
            ")",
        )

    op.create_index("ix_sources_organization_id", "sources", ["organization_id"])
    op.create_index("ix_sources_institution_id", "sources", ["institution_id"])
    op.create_index("ix_sources_teacher_id", "sources", ["teacher_id"])

    with op.batch_alter_table("source_revisions") as batch:
        batch.add_column(
            sa.Column("source_snapshot_checksum", sa.String(64), nullable=True)
        )
        batch.add_column(sa.Column("extracted_checksum", sa.String(64), nullable=True))
        batch.add_column(sa.Column("validated_checksum", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("approval_fingerprint", sa.String(64), nullable=True)
        )

    for item in revision_updates:
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
            item,
        )

    with op.batch_alter_table("source_revisions") as batch:
        batch.alter_column(
            "source_snapshot_checksum",
            existing_type=sa.String(64),
            nullable=False,
        )
        batch.drop_constraint("uq_source_revision_checksum", type_="unique")
        batch.drop_constraint("ck_source_revision_active_slot", type_="check")
        batch.create_unique_constraint(
            "uq_source_revision_identity",
            ["source_id", "checksum", "source_snapshot_checksum"],
        )
        batch.create_check_constraint(
            "ck_source_revision_active_slot",
            "(status = 'active' AND active_slot IS 1) OR "
            "(status <> 'active' AND active_slot IS NULL)",
        )

    op.create_index(
        "ix_source_revisions_source_snapshot_checksum",
        "source_revisions",
        ["source_snapshot_checksum"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_revisions_source_snapshot_checksum",
        table_name="source_revisions",
    )
    with op.batch_alter_table("source_revisions") as batch:
        batch.drop_constraint("ck_source_revision_active_slot", type_="check")
        batch.drop_constraint("uq_source_revision_identity", type_="unique")
        batch.create_unique_constraint(
            "uq_source_revision_checksum",
            ["source_id", "checksum"],
        )
        batch.create_check_constraint(
            "ck_source_revision_active_slot",
            "active_slot IS NULL OR (active_slot = 1 AND status = 'active')",
        )
        batch.drop_column("approval_fingerprint")
        batch.drop_column("validated_checksum")
        batch.drop_column("extracted_checksum")
        batch.drop_column("source_snapshot_checksum")

    op.drop_index("ix_sources_teacher_id", table_name="sources")
    op.drop_index("ix_sources_institution_id", table_name="sources")
    op.drop_index("ix_sources_organization_id", table_name="sources")

    with op.batch_alter_table("sources") as batch:
        batch.drop_constraint("ck_source_ownership_shape", type_="check")
        batch.drop_constraint(
            "ck_source_teacher_requires_institution",
            type_="check",
        )
        batch.drop_constraint(
            "ck_source_institution_requires_organization",
            type_="check",
        )
        batch.drop_constraint(
            "fk_source_teacher_same_institution",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_source_institution_same_organization",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_sources_teacher_id_teachers",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_sources_institution_id_institutions",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_sources_organization_id_organizations",
            type_="foreignkey",
        )
        batch.drop_column("teacher_id")
        batch.drop_column("institution_id")
        batch.drop_column("organization_id")
