"""C01 portable CHECK text shared by migrations and ORM metadata."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement

SOURCE_REVISION_ACTIVE_SLOT_CHECK = (
    "(status = 'active' AND active_slot IS NOT NULL AND active_slot = 1) "
    "OR (status <> 'active' AND active_slot IS NULL)"
)

_SUPPORTED_SYNTHETIC_DIALECTS = frozenset({"postgresql", "sqlite"})


def d13_synthetic_check_sql(dialect: str) -> str:
    """Exact synthetic marker containment — no lossy CAST/truthiness."""
    name = dialect.lower()
    if name == "postgresql":
        return "synthetic_test_only IS TRUE"
    if name == "sqlite":
        return "synthetic_test_only = 1"
    raise ValueError(f"unsupported dialect for synthetic check: {dialect}")


class _D13SyntheticMarkerCheck(ColumnElement[bool]):
    """Dialect-specific CHECK SQL for create_all / compiled DDL."""

    inherit_cache = True


@compiles(_D13SyntheticMarkerCheck)
def _compile_synthetic_marker_check(
    element: _D13SyntheticMarkerCheck,
    compiler: Any,
    **kw: Any,
) -> str:
    return d13_synthetic_check_sql(compiler.dialect.name)


D13_SYNTHETIC_MARKER_CHECK = _D13SyntheticMarkerCheck()