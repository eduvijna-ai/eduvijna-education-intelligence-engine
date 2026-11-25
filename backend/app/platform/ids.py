from __future__ import annotations

from uuid import UUID


def canonical_id(value: str) -> str:
    """Normalize API UUIDs to the hex form used for ORM string primary keys."""
    text = value.strip()
    try:
        return UUID(text).hex
    except ValueError:
        if len(text) == 32:
            return text.lower()
        raise