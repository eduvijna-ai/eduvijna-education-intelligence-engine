from __future__ import annotations

from app.mcp.server import mcp


def test_mcp_foundation_constructs() -> None:
    assert mcp is not None
