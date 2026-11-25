"""Shared helpers for C01 AT01–AT10 acceptance evidence (test-only)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

from tests.migration_test_support import (
    alembic_executable,
    backend_root,
    repository_alembic_head,
    run_alembic,
)

REV_0005 = "20261002_0005"
REV_0006 = "20261003_0006"
REV_0018 = "20261109_0018"
REV_0020 = "20261124_0020"
REV_0021 = "20261124_0021"

_ACCEPTANCE_MARKER = "c01_at_acceptance"


def acceptance_git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=backend_root().parent,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_alembic_url(
    database_url: str, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [alembic_executable(), "-c", str(backend_root() / "alembic.ini"), *args],
        cwd=backend_root(),
        env=environment,
        check=check,
        capture_output=True,
        text=True,
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def insert_replay_sqlite(
    connection: sqlite3.Connection,
    *,
    metadata: str,
    reservation_state: str = "reserved",
    owner_token: str | None = "owner-" + "c" * 58,
) -> str:
    row_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO d13_replay_reservations (
            id, created_at, updated_at, organization_id, institution_id,
            exam_pack_code, exam_version_id, academic_year,
            idempotency_key_hash, request_fingerprint, reservation_state,
            owner_token, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            row_id,
            now_iso(),
            now_iso(),
            "org-at",
            "inst-at",
            "pack",
            str(uuid.uuid4()),
            "2026",
            "a" * 64,
            "b" * 64,
            reservation_state,
            owner_token,
            metadata,
        ),
    )
    return row_id


def replay_rows_digest(connection: sqlite3.Connection) -> str:
    cols = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(d13_replay_reservations)")
    }
    base = [
        "id",
        "created_at",
        "updated_at",
        "organization_id",
        "institution_id",
        "exam_pack_code",
        "exam_version_id",
        "academic_year",
        "idempotency_key_hash",
        "request_fingerprint",
        "reservation_state",
        "owner_token",
        "metadata_json",
        "result_json",
        "payload_sha256",
        "result_snapshot_version",
    ]
    selected = [col for col in base if col in cols]
    if "synthetic_test_only" in cols:
        selected.append("synthetic_test_only")
    projection = ", ".join(selected)
    rows = connection.execute(
        f"SELECT {projection} FROM d13_replay_reservations ORDER BY id"
    ).fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def sqlite_schema_digest(connection: sqlite3.Connection) -> str:
    parts: list[str] = []
    for row in connection.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL ORDER BY type, name"
    ):
        parts.append(f"{row[0]}:{row[1]}:{row[2]}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def sqlite_table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def insert_minimal_source_sqlite(
    connection: sqlite3.Connection,
    *,
    title: str = "AT synthetic",
) -> str:
    source_id = str(uuid.uuid4())
    ts = now_iso()
    connection.execute(
        """
        INSERT INTO sources (
            id, source_type, title, trust_tier, status, metadata_json,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            source_id,
            "official_syllabus",
            title,
            "official_primary",
            "active",
            "{}",
            ts,
            ts,
        ),
    )
    return source_id


def insert_active_source_revision_sqlite(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    revision_number: int = 1,
) -> str:
    rev_id = str(uuid.uuid4())
    ts = now_iso()
    connection.execute(
        """
        INSERT INTO source_revisions (
            id, source_id, revision_number, ingestion_method, checksum,
            source_snapshot_checksum, content_type, byte_size, retrieved_at,
            extraction_status, extraction_metadata_json, status, active_slot,
            metadata_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            rev_id,
            source_id,
            revision_number,
            "manual",
            hashlib.sha256(f"{source_id}:{revision_number}".encode()).hexdigest()[:64],
            hashlib.sha256(f"snap:{source_id}:{revision_number}".encode()).hexdigest()[:64],
            "application/pdf",
            42,
            ts,
            "validated",
            "{}",
            "active",
            1,
            "{}",
            ts,
            ts,
        ),
    )
    return rev_id


def seed_minimal_nonempty_canonical(
    connection: sqlite3.Connection,
    *,
    include_replay: bool = True,
) -> dict[str, int]:
    org_id = str(uuid.uuid4())
    inst_id = str(uuid.uuid4())
    ts = now_iso()
    connection.execute(
        """
        INSERT INTO organizations (id, code, name, active, metadata_json, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (org_id, "AT-ORG", "AT Org", 1, "{}", ts, ts),
    )
    connection.execute(
        """
        INSERT INTO institutions (
            id, organization_id, code, name, active, metadata_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (inst_id, org_id, "AT-INST", "AT Inst", 1, "{}", ts, ts),
    )
    source_id = insert_minimal_source_sqlite(connection)
    insert_active_source_revision_sqlite(connection, source_id=source_id, revision_number=1)
    replay_id = ""
    if include_replay:
        cols = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(d13_replay_reservations)")
        }
        if "synthetic_test_only" in cols:
            row_id = str(uuid.uuid4())
            ts = now_iso()
            connection.execute(
                """
                INSERT INTO d13_replay_reservations (
                    id, created_at, updated_at, organization_id, institution_id,
                    exam_pack_code, exam_version_id, academic_year,
                    idempotency_key_hash, request_fingerprint, reservation_state,
                    owner_token, metadata_json, synthetic_test_only
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row_id,
                    ts,
                    ts,
                    org_id,
                    inst_id,
                    "pack",
                    str(uuid.uuid4()),
                    "2026",
                    "a" * 64,
                    "b" * 64,
                    "reserved",
                    "owner-" + "c" * 58,
                    '{"d13_synthetic_test_only": true, "c01_at": true}',
                    1,
                ),
            )
            replay_id = row_id
        else:
            replay_id = insert_replay_sqlite(
                connection,
                metadata='{"d13_synthetic_test_only": true, "c01_at": true}',
            )
    connection.commit()
    payload: dict[str, int | str] = {
        "organizations": 1,
        "institutions": 1,
        "sources": 1,
        "source_revisions": 1,
    }
    if include_replay:
        payload["d13_replay_reservations"] = 1
        payload["replay_row_id"] = replay_id
    return payload  # type: ignore[return-value]


@contextmanager
def restored_env(keys: tuple[str, ...]) -> Iterator[None]:
    saved = {key: os.environ.get(key) for key in keys}
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def pg_admin_url_from_disposable(url: str) -> str:
    parsed = urlparse(url)
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    driver = parsed.scheme
    return f"{driver}://{userinfo}{host}:{port}/postgres"


def owned_pg_database_name(prefix: str = "c01_at") -> str:
    token = uuid.uuid4().hex[:12]
    return f"{prefix}_{token}"


def create_owned_pg_database(admin_url: str, database_name: str) -> str:
    from tests.c01_disposable_pg import register_owned_database

    if not database_name.startswith("c01_at_"):
        raise ValueError("refusing to create non-owned database name")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        in_use = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": database_name},
        ).first()
        if in_use:
            raise RuntimeError(f"refusing to reuse existing database {database_name!r}")
        conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    register_owned_database(database_name)
    parsed = urlparse(admin_url)
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    driver = parsed.scheme
    return f"{driver}://{userinfo}{host}:{port}/{database_name}"


def drop_owned_pg_database(admin_url: str, database_name: str) -> None:
    from tests.c01_disposable_pg import assert_owned_database_registered

    assert_owned_database_registered(database_name)
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :name AND pid <> pg_backend_pid()
                """
            ),
            {"name": database_name},
        )
        conn.execute(text(f'DROP DATABASE "{database_name}"'))
    from tests.c01_disposable_pg import _OWNED_DATABASE_REGISTRY

    _OWNED_DATABASE_REGISTRY.discard(database_name)


def ensure_owned_disposable_pg_url() -> tuple[str, str, str]:
    """Allocate or reuse a registered owned database on the validated cluster."""
    from tests.c01_disposable_pg import (
        C01_PG_URL,
        parse_disposable_pg_url,
        validated_disposable_pg_cluster,
    )

    validated_disposable_pg_cluster()
    raw = os.environ[C01_PG_URL].strip()
    parsed = urlparse(raw)
    database_name = parsed.path.lstrip("/")
    admin_url = pg_admin_url_from_disposable(raw)
    if database_name.startswith("c01_at_"):
        url = parse_disposable_pg_url(raw, require_registry=True)
        return url, database_name, admin_url
    database_name = owned_pg_database_name()
    url = create_owned_pg_database(admin_url, database_name)
    return parse_disposable_pg_url(url, require_registry=True), database_name, admin_url


def sqlite_table_row_digest(connection: sqlite3.Connection, table: str) -> str:
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def insert_pg_replay_at_0020(conn, *, org_id: str, inst_id: str) -> str:
    row_id = str(uuid.uuid4())
    ts = now_iso()
    conn.execute(
        text(
            """
            INSERT INTO d13_replay_reservations (
                id, created_at, updated_at, organization_id, institution_id,
                exam_pack_code, exam_version_id, academic_year,
                idempotency_key_hash, request_fingerprint, reservation_state,
                owner_token, metadata_json
            ) VALUES (
                :id, CAST(:ts AS timestamptz), CAST(:ts AS timestamptz),
                :org, :inst, 'pack', :exam_ver, '2026',
                :idem, :fp, 'reserved', :owner,
                CAST(:meta AS json)
            )
            """
        ),
        {
            "id": row_id,
            "ts": ts,
            "org": org_id,
            "inst": inst_id,
            "exam_ver": str(uuid.uuid4()),
            "idem": "a" * 64,
            "fp": "b" * 64,
            "owner": "owner-" + "c" * 58,
            "meta": '{"d13_synthetic_test_only": true}',
        },
    )
    return row_id


def assert_pg_schema_empty(url: str) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_type = 'BASE TABLE'
                """
            )
        ).scalar_one()
        assert int(count) == 0


def canonical_row_digest(rows: list[tuple[object, ...]]) -> str:
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def revision_graph_token() -> str:
    graph_path = backend_root() / "migrations" / "c01_revision_graph.py"
    return hashlib.sha256(graph_path.read_bytes()).hexdigest()


__all__ = [
    "REV_0005",
    "REV_0006",
    "REV_0018",
    "REV_0020",
    "REV_0021",
    "_ACCEPTANCE_MARKER",
    "acceptance_git_sha",
    "canonical_row_digest",
    "create_owned_pg_database",
    "drop_owned_pg_database",
    "ensure_owned_disposable_pg_url",
    "insert_replay_sqlite",
    "owned_pg_database_name",
    "pg_admin_url_from_disposable",
    "replay_rows_digest",
    "repository_alembic_head",
    "restored_env",
    "revision_graph_token",
    "run_alembic",
    "run_alembic_url",
    "seed_minimal_nonempty_canonical",
    "sqlite_schema_digest",
    "sqlite_table_count",
    "sqlite_table_row_digest",
    "insert_pg_replay_at_0020",
]