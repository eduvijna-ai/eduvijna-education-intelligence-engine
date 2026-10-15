from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import Settings
from app.orchestration.exceptions import OrchestrationConfigurationError


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.split("postgresql+psycopg://", 1)[1]
    return url


class ManagedCheckpointer:
    """Holds a LangGraph checkpointer and releases backing resources on close."""

    def __init__(self, saver: object, *, closer: Any | None = None) -> None:
        self.saver = saver
        self._closer = closer

    def close(self) -> None:
        if self._closer is not None:
            self._closer()


def build_memory_checkpointer() -> MemorySaver:
    return MemorySaver()


@contextmanager
def sqlite_checkpointer(db_path: str) -> Iterator[SqliteSaver]:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def build_managed_checkpointer(
    settings: Settings, *, memory_only: bool = False
) -> ManagedCheckpointer:
    if memory_only:
        return ManagedCheckpointer(build_memory_checkpointer())
    url = settings.database_url
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        conn = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        return ManagedCheckpointer(saver, closer=conn.close)
    if url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver

        normalized = _normalize_postgres_url(url)
        cm = PostgresSaver.from_conn_string(normalized)
        pg_saver: object = cm.__enter__()
        assert isinstance(pg_saver, PostgresSaver)
        pg_saver.setup()
        return ManagedCheckpointer(pg_saver, closer=lambda: cm.__exit__(None, None, None))
    raise OrchestrationConfigurationError(
        f"Unsupported database_url for orchestration checkpoints: {url.split(':', 1)[0]}"
    )


def build_checkpointer(settings: Settings, *, memory_only: bool = False) -> object:
    return build_managed_checkpointer(settings, memory_only=memory_only).saver
