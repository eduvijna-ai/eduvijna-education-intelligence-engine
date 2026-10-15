from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.models.orchestration import (
    OrchestrationAuditEvent,
    OrchestrationCheckpointLease,
    OrchestrationGenerationCall,
    OrchestrationIdempotencyRecord,
)

_CONTROL_TABLES = (
    OrchestrationAuditEvent.__table__,
    OrchestrationIdempotencyRecord.__table__,
    OrchestrationGenerationCall.__table__,
    OrchestrationCheckpointLease.__table__,
)


def _sqlite_memory_database(bind: object) -> bool:
    dialect = getattr(bind, "dialect", None)
    if dialect is None or dialect.name != "sqlite":
        return False
    if isinstance(bind, Connection):
        engine = bind.engine
        database = engine.url.database
    elif isinstance(bind, Engine):
        database = bind.url.database
    else:
        url = getattr(bind, "url", None)
        database = url.database if url is not None else None
    return not database or database == ":memory:"


def _sqlite_database_path(bind: object) -> str | None:
    dialect = getattr(bind, "dialect", None)
    if dialect is None or dialect.name != "sqlite":
        return None
    if isinstance(bind, Connection):
        database = bind.engine.url.database
    elif isinstance(bind, Engine):
        database = bind.url.database
    else:
        url = getattr(bind, "url", None)
        database = url.database if url is not None else None
    if not database or database == ":memory:":
        return None
    return str(database)


def _open_sqlite_control_session(database_path: str) -> Session:
    control_path = f"{database_path}.orchestration.sqlite"
    Path(control_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{control_path}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA busy_timeout=30000")
    Base.metadata.create_all(engine, tables=list(_CONTROL_TABLES))
    return Session(bind=engine, expire_on_commit=False)


def open_control_session(domain_session: Session) -> Session:
    """Independent durable session for idempotency, leases, calls, and audit."""
    bind = domain_session.get_bind()
    if bind is None:
        raise RuntimeError("domain session has no bind")
    if _sqlite_memory_database(bind):
        return Session(
            bind=domain_session.connection(),
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
    sqlite_path = _sqlite_database_path(bind)
    if sqlite_path is not None:
        return _open_sqlite_control_session(sqlite_path)
    return Session(bind=bind, expire_on_commit=False)


def commit_control(session: Session) -> None:
    bind = session.get_bind()
    if bind is not None and _sqlite_memory_database(bind):
        session.flush()
        return
    session.commit()
