from alembic.config import Config

from app.db.alembic import escape_alembic_config_value


def test_alembic_url_preserves_percent_encoded_credentials() -> None:
    database_url = "postgresql+psycopg://user:p%40ss@example.test/eduvijna"
    config = Config()
    config.set_main_option(
        "sqlalchemy.url",
        escape_alembic_config_value(database_url),
    )
    assert config.get_main_option("sqlalchemy.url") == database_url
