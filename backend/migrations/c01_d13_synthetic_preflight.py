"""C01 Package S: strict read-only eligibility for migration 0021 (abort-only)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from migrations.c01_constraints import d13_synthetic_check_sql
from migrations.c01_revision_graph import REV_0021, is_at_or_past_revision

D13_SYNTHETIC_TEST_ONLY_KEY = "d13_synthetic_test_only"
_SUPPORTED_DIALECTS = frozenset({"postgresql", "sqlite"})
_VALID_STATES = frozenset({"reserved", "in_progress", "replayed"})


class LegacyAuditStatus(StrEnum):
    CLEAN = "clean"
    UNTRUSTED_FLAGS = "untrusted_flags"
    COLUMN_ABSENT = "column_absent"
    WRONG_VERSION = "wrong_version"
    WRONG_REVISION = "wrong_revision"
    SCHEMA_MISMATCH = "schema_mismatch"
    PARTIAL_APPLY = "partial_apply"
    VERSION_ROW_INVALID = "version_row_invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LegacyAuditReport:
    status: LegacyAuditStatus
    revision: str | None
    untrusted_row_ids: tuple[str, ...]
    detail: str = ""


def _reject_non_finite(value: object) -> None:
    if isinstance(value, float) and (value != value or abs(value) == float("inf")):
        raise ValueError("non-finite number")


def _walk_finite(value: object) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _walk_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _walk_finite(nested)
    elif isinstance(value, float):
        _reject_non_finite(value)


def strict_eligible_from_raw(raw: str) -> bool:
    """True only for root-object JSON with a single boolean true marker."""
    if not raw or not str(raw).strip():
        return False
    try:

        def pair_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            keys = [key for key, _ in pairs]
            if len(keys) != len(set(keys)):
                raise ValueError("duplicate keys")
            obj = dict(pairs)
            _walk_finite(obj)
            return obj

        def reject_constants(_: str) -> None:
            raise ValueError("invalid constant")

        parsed = json.loads(raw, object_pairs_hook=pair_hook, parse_constant=reject_constants)
    except (json.JSONDecodeError, ValueError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    if D13_SYNTHETIC_TEST_ONLY_KEY not in parsed:
        return False
    marker = parsed[D13_SYNTHETIC_TEST_ONLY_KEY]
    return marker is True


def _row_state_consistent(
    state: str,
    result_json: object,
    payload_sha256: object,
    result_snapshot_version: object,
    owner_token: object,
) -> bool:
    """Match 0020 CHECK + durable replay envelope integrity (pending rows keep owner_token)."""
    if state not in _VALID_STATES:
        return False
    if state in ("reserved", "in_progress"):
        return (
            owner_token is not None
            and str(owner_token).strip() != ""
            and result_json is None
            and payload_sha256 is None
            and result_snapshot_version is None
        )
    if state == "replayed":
        return (
            owner_token is None
            and payload_sha256 is not None
            and result_json is not None
            and result_snapshot_version is not None
        )
    return False


def _lock_replay_table(connection: Connection) -> None:
    dialect = connection.dialect.name
    if dialect == "postgresql":
        connection.execute(text("LOCK TABLE d13_replay_reservations IN ACCESS EXCLUSIVE MODE"))


def assert_0021_preflight(connection: Connection) -> None:
    """Abort migration before any DDL if any row fails strict marker eligibility."""
    dialect = connection.dialect.name
    if dialect not in _SUPPORTED_DIALECTS:
        raise RuntimeError(f"0021 preflight unsupported dialect: {dialect}")

    _lock_replay_table(connection)

    if dialect == "postgresql":
        sql = text(
            "SELECT id, metadata_json::text AS raw, reservation_state, "
            "result_json, payload_sha256, result_snapshot_version, owner_token "
            "FROM d13_replay_reservations"
        )
    else:
        sql = text(
            "SELECT id, CAST(metadata_json AS TEXT) AS raw, reservation_state, "
            "result_json, payload_sha256, result_snapshot_version, owner_token "
            "FROM d13_replay_reservations"
        )
    rows = connection.execute(sql).fetchall()

    for row in rows:
        row_id = str(row[0])
        raw = row[1]
        if not isinstance(raw, str):
            raise RuntimeError(
                f"0021 preflight abort: reservation {row_id} metadata is not raw text"
            )
        state = str(row[2])
        if not _row_state_consistent(state, row[3], row[4], row[5], row[6]):
            raise RuntimeError(
                f"0021 preflight abort: reservation {row_id} replay state/payload inconsistent"
            )
        if not strict_eligible_from_raw(raw):
            raise RuntimeError(
                f"0021 preflight abort: reservation {row_id} "
                "lacks strict JSON boolean true marker"
            )


def assert_all_rows_synthetic_true(connection: Connection) -> None:
    dialect = connection.dialect.name
    check = d13_synthetic_check_sql(dialect)
    bad = int(
        connection.execute(
            text(f"SELECT COUNT(*) FROM d13_replay_reservations WHERE NOT ({check})")
        ).scalar_one()
    )
    if bad:
        raise RuntimeError(f"0021 post-update verify failed: {bad} row(s) not synthetic true")


def _synthetic_column_present(connection: Connection, dialect: str) -> dict[str, object] | None:
    if dialect == "postgresql":
        row = connection.execute(
            text(
                """
                SELECT data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'd13_replay_reservations'
                  AND column_name = 'synthetic_test_only'
                """
            )
        ).mappings().first()
        return dict(row) if row else None
    info = connection.execute(text("PRAGMA table_info(d13_replay_reservations)")).fetchall()
    for col in info:
        if str(col[1]) == "synthetic_test_only":
            return {
                "data_type": str(col[2]),
                "is_nullable": "NO" if col[3] == 1 else "YES",
                "column_default": col[4],
            }
    return None


def _expected_synthetic_check_in_ddl(connection: Connection, dialect: str) -> bool:
    expected_fragment = (
        "synthetic_test_only IS TRUE" if dialect == "postgresql" else "synthetic_test_only = 1"
    )
    if dialect == "postgresql":
        row = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) AS def
                FROM pg_constraint
                WHERE conname = 'ck_d13_replay_synthetic_marker'
                """
            )
        ).mappings().first()
        if row is None:
            return False
        return expected_fragment in str(row["def"])
    ddl = connection.execute(
        text(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='d13_replay_reservations'"
        )
    ).scalar_one_or_none()
    if ddl is None:
        return False
    return expected_fragment in str(ddl)


def audit_legacy_0021_state(connection: Connection) -> LegacyAuditReport:
    dialect = connection.dialect.name
    if dialect not in _SUPPORTED_DIALECTS:
        return LegacyAuditReport(LegacyAuditStatus.UNKNOWN, None, (), f"unsupported {dialect}")

    version_rows = connection.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    if len(version_rows) != 1:
        return LegacyAuditReport(
            LegacyAuditStatus.VERSION_ROW_INVALID,
            None,
            (),
            f"expected 1 alembic_version row, got {len(version_rows)}",
        )
    revision = str(version_rows[0][0])

    col = _synthetic_column_present(connection, dialect)
    at_or_past_0021 = is_at_or_past_revision(revision, REV_0021)

    if col is None:
        if at_or_past_0021:
            return LegacyAuditReport(
                LegacyAuditStatus.PARTIAL_APPLY,
                revision,
                (),
                "at/past 0021 graph index but synthetic_test_only column missing",
            )
        return LegacyAuditReport(LegacyAuditStatus.COLUMN_ABSENT, revision, ())

    if not at_or_past_0021:
        return LegacyAuditReport(
            LegacyAuditStatus.WRONG_REVISION,
            revision,
            (),
            "synthetic column present but alembic revision before 0021",
        )

    if dialect == "postgresql":
        if str(col.get("data_type")).lower() != "boolean":
            return LegacyAuditReport(
                LegacyAuditStatus.SCHEMA_MISMATCH,
                revision,
                (),
                f"expected boolean column, got {col.get('data_type')}",
            )
        if str(col.get("is_nullable")).upper() != "NO":
            return LegacyAuditReport(
                LegacyAuditStatus.SCHEMA_MISMATCH,
                revision,
                (),
                "synthetic_test_only must be NOT NULL",
            )
    else:
        if str(col.get("data_type")).upper() not in {"BOOLEAN", "NUM", "INTEGER"}:
            return LegacyAuditReport(
                LegacyAuditStatus.SCHEMA_MISMATCH,
                revision,
                (),
                f"unexpected sqlite column type {col.get('data_type')}",
            )
        if str(col.get("is_nullable")).upper() != "NO":
            return LegacyAuditReport(
                LegacyAuditStatus.SCHEMA_MISMATCH,
                revision,
                (),
                "synthetic_test_only must be NOT NULL",
            )

    if not _expected_synthetic_check_in_ddl(connection, dialect):
        return LegacyAuditReport(
            LegacyAuditStatus.SCHEMA_MISMATCH,
            revision,
            (),
            "missing or wrong ck_d13_replay_synthetic_marker DDL",
        )

    if dialect == "postgresql":
        row_sql = text(
            "SELECT id, metadata_json::text, synthetic_test_only "
            "FROM d13_replay_reservations"
        )
    else:
        row_sql = text(
            "SELECT id, CAST(metadata_json AS TEXT), synthetic_test_only "
            "FROM d13_replay_reservations"
        )
    untrusted: list[str] = []
    for row in connection.execute(row_sql).fetchall():
        row_id, raw, flag = str(row[0]), row[1], row[2]
        if dialect == "sqlite":
            stored_true = flag == 1
        else:
            stored_true = flag is True
        eligible = (
            strict_eligible_from_raw(raw) if raw is not None and isinstance(raw, str) else False
        )
        if stored_true and not eligible:
            untrusted.append(row_id)
        elif eligible and not stored_true:
            untrusted.append(row_id)

    if untrusted:
        return LegacyAuditReport(
            LegacyAuditStatus.UNTRUSTED_FLAGS,
            revision,
            tuple(untrusted),
            "legacy integer promotion or metadata mismatch",
        )
    return LegacyAuditReport(LegacyAuditStatus.CLEAN, revision, ())