from __future__ import annotations

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


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


def open_control_session(domain_session: Session) -> Session:
    """Independent session for orchestration durability (idempotency, leases, generation calls)."""
    bind = domain_session.get_bind()
    if bind is None:
        raise RuntimeError("domain session has no bind")
    if _sqlite_memory_database(bind):
        return Session(
            bind=domain_session.connection(),
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
    return Session(bind=bind, expire_on_commit=False)


def commit_control(session: Session) -> None:
    bind = session.get_bind()
    if bind is not None and _sqlite_memory_database(bind):
        session.flush()
        return
    session.commit()
