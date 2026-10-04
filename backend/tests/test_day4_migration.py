from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database_url: str) -> Config:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def test_day4_migration_upgrade_downgrade_reupgrade_preserves_prior_data(
    tmp_path: Path,
) -> None:
    database = tmp_path / "day4-migration.db"
    database_url = f"sqlite:///{database}"
    config = _config(database_url)

    command.upgrade(config, "20261003_0007")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO education_frameworks "
                "(id, code, name, country, active, created_at, updated_at) "
                "VALUES "
                "('framework-before-d4', 'pre-d4', 'Pre Day 4', 'India', 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    command.upgrade(config, "20261004_0008")
    inspector = inspect(engine)
    assert "curriculum_alignments" in inspector.get_table_names()
    assert "assessment_evidence" in inspector.get_table_names()
    framework_columns = {
        column["name"] for column in inspector.get_columns("education_frameworks")
    }
    expected_columns = {
        "authority",
        "version_code",
        "source_revision_id",
        "source_locator",
    }
    assert expected_columns <= framework_columns

    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT COUNT(*) FROM education_frameworks WHERE id='framework-before-d4'")
        ) == 1

    command.downgrade(config, "20261003_0007")
    inspector = inspect(engine)
    assert "curriculum_alignments" not in inspector.get_table_names()
    assert "assessment_evidence" not in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT COUNT(*) FROM education_frameworks WHERE id='framework-before-d4'")
        ) == 1

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert "curriculum_alignments" in inspector.get_table_names()
    assert "assessment_evidence" in inspector.get_table_names()
    engine.dispose()
