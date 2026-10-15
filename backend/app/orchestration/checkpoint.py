from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import Settings


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


def build_checkpointer(settings: Settings, *, memory_only: bool = False) -> object:
    if memory_only:
        return build_memory_checkpointer()
    url = settings.database_url
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        conn = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        return saver
    if url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver

        return PostgresSaver.from_conn_string(url)
    return build_memory_checkpointer()
