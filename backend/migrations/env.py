from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.alembic import escape_alembic_config_value
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    escape_alembic_config_value(get_settings().database_url),
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sqlite_migrations(connection: object) -> None:
    # SQLite batch table recreation must disable FK actions, but DDL and the
    # alembic_version update still need one explicit transaction so any failure
    # restores the previous schema and revision atomically.
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")  # type: ignore[attr-defined]
    connection.commit()  # type: ignore[attr-defined]

    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transactional_ddl=True,
        )
        connection.exec_driver_sql("BEGIN IMMEDIATE")  # type: ignore[attr-defined]
        try:
            context.run_migrations()
            violations = connection.exec_driver_sql(  # type: ignore[attr-defined]
                "PRAGMA foreign_key_check"
            ).fetchall()
            if violations:
                raise RuntimeError(
                    "SQLite foreign-key violations after migration: "
                    + repr(violations[:20])
                )
            connection.commit()  # type: ignore[attr-defined]
        except Exception:
            connection.rollback()  # type: ignore[attr-defined]
            raise
    finally:
        if connection.in_transaction():  # type: ignore[attr-defined]
            connection.rollback()  # type: ignore[attr-defined]
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]
        enabled = connection.exec_driver_sql(  # type: ignore[attr-defined]
            "PRAGMA foreign_keys"
        ).scalar_one()
        if enabled != 1:
            raise RuntimeError("SQLite foreign-key enforcement could not be restored")


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            _run_sqlite_migrations(connection)
            return

        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
