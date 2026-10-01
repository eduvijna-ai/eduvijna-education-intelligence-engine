def escape_alembic_config_value(value: str) -> str:
    """Escape percent signs so ConfigParser preserves URL percent-encoding."""
    return value.replace("%", "%%")
