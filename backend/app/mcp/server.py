from __future__ import annotations

from typing import Any

from mcp.server import MCPServer


def create_mcp_server() -> Any:
    server = MCPServer("eduvijna")

    @server.tool()
    def health() -> dict[str, str]:
        """Return the Day-1 MCP foundation health status."""
        return {"service": "eduvijna-mcp", "status": "ok"}

    return server


mcp = create_mcp_server()
