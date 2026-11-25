from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from app.platform.mcp.auth import mcp_transport_configured, require_mcp_startup_gate

_MCP_CATALOG_DISABLED_REASON = (
    "MCP catalogue tools are disabled until authenticated Streamable HTTP transport "
    "is accepted; only health is exposed (R3-02)."
)


def create_mcp_server() -> Any:
    require_mcp_startup_gate()
    server = MCPServer("eduvijna")

    @server.tool()
    def health() -> dict[str, str]:
        """Return the MCP transport health status."""
        configured = str(mcp_transport_configured())
        return {
            "service": "eduvijna-mcp",
            "status": "ok",
            "auth_configured": configured,
            "catalog_exposure": "disabled",
            "catalog_reason": _MCP_CATALOG_DISABLED_REASON,
        }

    return server


def mcp_catalog_enabled() -> bool:
    return False


mcp = create_mcp_server()


if __name__ == "__main__":
    mcp.run()