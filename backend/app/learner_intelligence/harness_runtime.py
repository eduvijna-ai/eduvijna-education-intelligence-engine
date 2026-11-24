"""Isolated synthetic harness session — sole authorized mutation path (D15 R3-01)."""

from __future__ import annotations

import secrets
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import create_database_engine, enable_sqlite_foreign_keys
from app.learner_intelligence.contracts import TrustedActorContext
from app.learner_intelligence.fixtures import seed_synthetic_tenant

HARNESS_SESSION_KEY = "d15_harness_authorized"
HARNESS_BIND_KEY = "d15_harness_binding_secret"
HARNESS_OWNED_KEY = "d15_harness_owned"


def authorize_harness_session(session: Session) -> str:
    """Mark session as harness-owned; returns binding secret stored on attempts."""

    session.info[HARNESS_SESSION_KEY] = True
    binding = secrets.token_hex(16)
    session.info[HARNESS_BIND_KEY] = binding
    return binding


def harness_session_authorized(session: Session, *, expected_binding: str | None = None) -> bool:
    if not session.info.get(HARNESS_SESSION_KEY):
        return False
    if expected_binding is None:
        return True
    return session.info.get(HARNESS_BIND_KEY) == expected_binding


def reject_non_harness_session() -> bool:
    return False


@contextmanager
def isolated_harness_session(
    database_url: str | None = None,
) -> Generator[tuple[Session, str, TrustedActorContext], None, None]:
    """Fresh ephemeral DB with fixed synthetic tenant; harness owns commit."""

    url = database_url or "sqlite:///:memory:"
    engine = create_database_engine(url)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    binding = authorize_harness_session(session)
    session.info[HARNESS_OWNED_KEY] = True
    actor = seed_synthetic_tenant(session)
    session.flush()
    try:
        yield session, binding, actor
        if session.info.get(HARNESS_OWNED_KEY):
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ephemeral_file_harness(tmp_path: Path) -> str:
    db = tmp_path / "d15-harness.sqlite"
    return f"sqlite:///{db}"