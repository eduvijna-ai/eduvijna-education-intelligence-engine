from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.core.config import get_settings

REQUIRED_REVISION = "20261002_0005"
REPAIR_KEY = "_day3_ownership_repair"
TENANT_TYPES = {"institution_content", "teacher_content"}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


def _current_revision(connection: Any) -> str | None:
    row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
    return str(row[0]) if row is not None else None


def _require_0005(connection: Any) -> None:
    current = _current_revision(connection)
    if current != REQUIRED_REVISION:
        raise RuntimeError(
            "legacy ownership repair is only valid before the Day-3 compatibility "
            f"migration; expected {REQUIRED_REVISION}, found {current!r}"
        )


def inspect_pending(connection: Any) -> list[dict[str, Any]]:
    _require_0005(connection)
    rows = connection.execute(
        text(
            """
            SELECT id, source_type, title, metadata_json
            FROM sources
            WHERE source_type IN ('institution_content', 'teacher_content')
            ORDER BY id
            """
        )
    ).mappings()
    result: list[dict[str, Any]] = []
    for row in rows:
        metadata = _json_object(row["metadata_json"])
        repair = metadata.get(REPAIR_KEY)
        result.append(
            {
                "source_id": str(row["id"]),
                "source_type": str(row["source_type"]),
                "title": str(row["title"]),
                "repair_staged": isinstance(repair, dict),
                "repair": repair if isinstance(repair, dict) else None,
            }
        )
    return result


def _validate_mapping(
    connection: Any,
    *,
    source_id: str,
    source_type: str,
    mapping: dict[str, Any],
) -> dict[str, str | None]:
    organization_id = mapping.get("organization_id")
    institution_id = mapping.get("institution_id")
    teacher_id = mapping.get("teacher_id")

    if not isinstance(organization_id, str) or not isinstance(institution_id, str):
        raise ValueError(
            f"{source_id}: organization_id and institution_id are required strings"
        )
    if source_type == "institution_content" and teacher_id is not None:
        raise ValueError(f"{source_id}: institution_content cannot set teacher_id")
    if source_type == "teacher_content" and not isinstance(teacher_id, str):
        raise ValueError(f"{source_id}: teacher_content requires teacher_id")

    organization = connection.execute(
        text("SELECT id FROM organizations WHERE id = :id"),
        {"id": organization_id},
    ).first()
    if organization is None:
        raise ValueError(f"{source_id}: organization_id does not exist")

    institution = connection.execute(
        text(
            """
            SELECT organization_id
            FROM institutions
            WHERE id = :id
            """
        ),
        {"id": institution_id},
    ).mappings().first()
    if institution is None or str(institution["organization_id"]) != organization_id:
        raise ValueError(
            f"{source_id}: institution does not belong to organization"
        )

    if teacher_id is not None:
        teacher = connection.execute(
            text(
                """
                SELECT institution_id
                FROM teachers
                WHERE id = :id
                """
            ),
            {"id": teacher_id},
        ).mappings().first()
        if teacher is None or str(teacher["institution_id"]) != institution_id:
            raise ValueError(
                f"{source_id}: teacher does not belong to institution"
            )

    return {
        "organization_id": organization_id,
        "institution_id": institution_id,
        "teacher_id": teacher_id if isinstance(teacher_id, str) else None,
    }


def apply_mapping(connection: Any, mapping_path: Path) -> list[str]:
    _require_0005(connection)
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ownership mapping must be a JSON object keyed by source id")

    source_rows = list(
        connection.execute(
            text(
                """
                SELECT id, source_type, metadata_json
                FROM sources
                WHERE source_type IN ('institution_content', 'teacher_content')
                ORDER BY id
                """
            )
        ).mappings()
    )
    expected_ids = {str(row["id"]) for row in source_rows}
    supplied_ids = set(payload)
    if supplied_ids != expected_ids:
        missing = sorted(expected_ids - supplied_ids)
        unknown = sorted(supplied_ids - expected_ids)
        raise ValueError(
            "ownership mapping must cover every legacy tenant source exactly; "
            f"missing={missing}, unknown={unknown}"
        )

    updated: list[str] = []
    for row in source_rows:
        source_id = str(row["id"])
        raw_mapping = payload[source_id]
        if not isinstance(raw_mapping, dict):
            raise ValueError(f"{source_id}: mapping must be an object")
        validated = _validate_mapping(
            connection,
            source_id=source_id,
            source_type=str(row["source_type"]),
            mapping=raw_mapping,
        )

        metadata = _json_object(row["metadata_json"])
        metadata[REPAIR_KEY] = validated
        connection.execute(
            text(
                """
                UPDATE sources
                SET metadata_json = :metadata_json
                WHERE id = :source_id
                """
            ),
            {
                "metadata_json": json.dumps(
                    metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "source_id": source_id,
            },
        )
        updated.append(source_id)

    return updated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage explicit ownership for legacy Day-3 tenant sources"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--mapping", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    engine = create_engine(get_settings().database_url)
    if args.command == "inspect":
        with engine.connect() as connection:
            print(json.dumps(inspect_pending(connection), indent=2, sort_keys=True))
        return

    with engine.begin() as connection:
        updated = apply_mapping(connection, args.mapping)
    print(
        json.dumps(
            {"updated_source_ids": updated},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
