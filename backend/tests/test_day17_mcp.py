from __future__ import annotations

import pytest

from app.mcp.server import mcp_catalog_enabled
from app.platform.auth.principal import RequestPrincipal
from app.platform.errors import CapabilityNotReadyError
from app.platform.mcp.tools import mcp_get_capabilities, mcp_tool_router


def test_mcp_catalog_transport_disabled() -> None:
    assert mcp_catalog_enabled() is False


def test_mcp_lists_capabilities_with_principal() -> None:
    principal = RequestPrincipal(
        principal_id="p1",
        organization_id="o1",
        institution_id="i1",
        role="teacher",
        scopes=("capabilities:read", "mcp:invoke"),
        actor_kind="teacher",
        actor_ref="t1",
        auth_method="harness",
    )
    payload = mcp_get_capabilities(principal=principal)
    assert len(payload["capabilities"]) >= 10
    assert payload["containment"]["day15_learner_hold"] is True


def test_mcp_blocks_learner_tool() -> None:
    principal = RequestPrincipal(
        principal_id="p1",
        organization_id="o1",
        institution_id="i1",
        role="teacher",
        scopes=("mcp:invoke", "learners:read"),
        actor_kind="teacher",
        actor_ref="t1",
        auth_method="harness",
    )
    with pytest.raises(CapabilityNotReadyError):
        mcp_tool_router("get_learner_diagnostics", {}, principal=principal)
