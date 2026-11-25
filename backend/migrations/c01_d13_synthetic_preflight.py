"""C01 Gate B: strict read-only eligibility for migration 0021 (abort-only)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

D13_SYNTHETIC_TEST_ONLY_KEY = "d13_synthetic_test_only"


def _reject_non_finite(value: object) -> None:
    if isinstance(value, float) and (value != value or abs(value) == float("inf")):
        raise ValueError("non-finite number")


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
            for value in obj.values():
                _reject_non_finite(value)
            return obj

        def _reject_constants(_: str) -> None:
            raise ValueError("invalid constant")

        parsed = json.loads(raw, object_pairs_hook=pair_hook, parse_constant=_reject_constants)
    except (json.JSONDecodeError, ValueError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    if D13_SYNTHETIC_TEST_ONLY_KEY not in parsed:
        return False
    marker = parsed[D13_SYNTHETIC_TEST_ONLY_KEY]
    return marker is True


def _row_metadata_raw(connection: Connection, row_id: str, raw: object) -> str:
    if isinstance(raw, (dict, list)):
        # Deserialized JSON loses duplicate-key evidence; refuse unless we have text.
        dialect = connection.dialect.name
        if dialect == "postgresql":
            again = connection.execute(
                text("SELECT metadata_json::text FROM d13_replay_reservations WHERE id = :id"),
                {"id": row_id},
            ).scalar_one()
            return str(again)
        return json.dumps(raw, separators=(",", ":"), sort_keys=False)
    return str(raw)


def assert_0021_preflight(connection: Connection) -> None:
    """Abort migration before any DDL if any row fails strict marker eligibility."""
    dialect = connection.dialect.name
    if dialect == "postgresql":
        rows = connection.execute(
            text(
                "SELECT id, metadata_json::text AS raw "
                "FROM d13_replay_reservations FOR UPDATE"
            )
        ).fetchall()
    else:
        rows = connection.execute(
            text("SELECT id, metadata_json AS raw FROM d13_replay_reservations")
        ).fetchall()

    for row in rows:
        row_id = str(row[0])
        raw = _row_metadata_raw(connection, row_id, row[1])
        if not strict_eligible_from_raw(raw):
            raise RuntimeError(
                f"0021 preflight abort: reservation {row_id} "
                "lacks strict JSON boolean true marker"
            )


def assert_all_rows_synthetic_true(connection: Connection) -> None:
    dialect = connection.dialect.name
    if dialect == "postgresql":
        sql = text(
            "SELECT COUNT(*) FROM d13_replay_reservations "
            "WHERE synthetic_test_only IS NOT TRUE"
        )
    else:
        sql = text(
            "SELECT COUNT(*) FROM d13_replay_reservations "
            "WHERE synthetic_test_only IS NOT 1"
        )
    bad = int(connection.execute(sql).scalar_one())
    if bad:
        raise RuntimeError(f"0021 post-update verify failed: {bad} row(s) not synthetic true")