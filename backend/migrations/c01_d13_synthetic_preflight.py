"""C01 Gate B: strict read-only eligibility for migration 0021 (abort-only)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from migrations.c01_constraints import d13_synthetic_check_sql

D13_SYNTHETIC_TEST_ONLY_KEY = "d13_synthetic_test_only"
_SUPPORTED_DIALECTS = frozenset({"postgresql", "sqlite"})


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


def _row_state_consistent(state: str, result_json: object, payload_sha256: object) -> bool:
    """Align with 0020 ck_d13_replay_pending_no_payload (preflight only)."""
    if state in ("reserved", "in_progress"):
        return result_json is None and payload_sha256 is None
    return True


def _lock_replay_table(connection: Connection) -> None:
    dialect = connection.dialect.name
    if dialect == "postgresql":
        connection.execute(text("LOCK TABLE d13_replay_reservations IN ACCESS EXCLUSIVE MODE"))
    # SQLite: Alembic runs this migration in a single explicit transaction (env.py).


def assert_0021_preflight(connection: Connection) -> None:
    """Abort migration before any DDL if any row fails strict marker eligibility."""
    dialect = connection.dialect.name
    if dialect not in _SUPPORTED_DIALECTS:
        raise RuntimeError(f"0021 preflight unsupported dialect: {dialect}")

    _lock_replay_table(connection)

    if dialect == "postgresql":
        sql = text(
            "SELECT id, metadata_json::text AS raw, reservation_state, "
            "result_json, payload_sha256 "
            "FROM d13_replay_reservations"
        )
    else:
        sql = text(
            "SELECT id, CAST(metadata_json AS TEXT) AS raw, reservation_state, "
            "result_json, payload_sha256 "
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
        if not _row_state_consistent(state, row[3], row[4]):
            raise RuntimeError(
                f"0021 preflight abort: reservation {row_id} inconsistent pending payload"
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


def audit_untrusted_legacy_flags(connection: Connection) -> list[str]:
    """Read-only: rows with synthetic_test_only set but metadata not strict-eligible."""
    dialect = connection.dialect.name
    if dialect == "postgresql":
        cols = connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='d13_replay_reservations' "
                "AND column_name='synthetic_test_only'"
            )
        ).fetchall()
        if not cols:
            return []
        rows = connection.execute(
            text(
                "SELECT id, metadata_json::text, synthetic_test_only "
                "FROM d13_replay_reservations"
            )
        ).fetchall()
    else:
        info = connection.execute(text("PRAGMA table_info(d13_replay_reservations)")).fetchall()
        if not any(str(c[1]) == "synthetic_test_only" for c in info):
            return []
        rows = connection.execute(
            text(
                "SELECT id, CAST(metadata_json AS TEXT), synthetic_test_only "
                "FROM d13_replay_reservations"
            )
        ).fetchall()
    untrusted: list[str] = []
    for row_id, raw, flag in rows:
        if not flag:
            continue
        if isinstance(raw, str) and not strict_eligible_from_raw(raw):
            untrusted.append(str(row_id))
    return untrusted