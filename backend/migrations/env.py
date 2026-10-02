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


def _set_sqlite_foreign_keys(connection: object, enabled: bool) -> None:
    # SQLite table-recreation migrations must run with FK actions disabled or
    # dropping the old parent table can cascade-delete valid child rows.
    value = "ON" if enabled else "OFF"
    connection.exec_driver_sql(f"PRAGMA foreign_keys={value}")  # type: ignore[attr-defined]
    connection.commit()  # type: ignore[attr-defined]


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        if is_sqlite:
            _set_sqlite_foreign_keys(connection, False)

        migration_succeeded = False
        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
            migration_succeeded = True

            if is_sqlite:
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(
                        "SQLite foreign-key violations after migration: "
                        + repr(violations[:20])
                    )
                if connection.in_transaction():
                    connection.commit()
        finally:
            if is_sqlite:
                if connection.in_transaction():
                    connection.rollback()
                _set_sqlite_foreign_keys(connection, True)

        if not migration_succeeded:
            raise RuntimeError("migration did not complete successfully")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
