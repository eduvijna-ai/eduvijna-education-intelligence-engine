from __future__ import annotations

import pytest

from app.platform.errors import CapabilityNotReadyError
from app.platform.mcp.tools import mcp_get_capabilities, mcp_tool_router


def test_mcp_lists_capabilities() -> None:
    payload = mcp_get_capabilities()
    assert len(payload["capabilities"]) >= 10
    assert payload["containment"]["day15_learner_hold"] is True


def test_mcp_blocks_learner_tool() -> None:
    from app.platform.errors import AuthenticationError

    with pytest.raises((CapabilityNotReadyError, AuthenticationError)):
        mcp_tool_router("get_learner_diagnostics", {}, principal=None)
