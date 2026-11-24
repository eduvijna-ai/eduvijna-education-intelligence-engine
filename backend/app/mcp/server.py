from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from app.platform.mcp.tools import mcp_get_capabilities, mcp_tool_router

MCP_TOOL_NAMES = (
    "get_capabilities",
    "search_curriculum",
    "search_knowledge",
    "get_exam_pattern",
    "generate_questions",
    "validate_question",
    "generate_mock_exam",
    "get_job_status",
    "analyze_attempt",
    "diagnose_answer",
    "get_learner_diagnostics",
    "get_prerequisite_gaps",
    "get_misconceptions",
    "recommend_remediation",
    "generate_diagnostic_assessment",
)


def _require_mcp_api_key() -> None:
    expected = (os.environ.get("MCP_API_KEY") or "").strip()
    if not expected:
        return
    provided = (os.environ.get("MCP_RUNTIME_API_KEY") or "").strip()
    if provided != expected:
        raise PermissionError("MCP API key required")


def create_mcp_server() -> Any:
    server = MCPServer("eduvijna")

    @server.tool()
    def health() -> dict[str, str]:
        """Return the MCP transport health status."""
        return {"service": "eduvijna-mcp", "status": "ok"}

    @server.tool()
    def get_capabilities() -> dict[str, object]:
        """List server-owned capability readiness (no caller overrides)."""
        _require_mcp_api_key()
        return mcp_get_capabilities()

    @server.tool()
    def invoke_catalog_tool(tool_name: str, arguments_json: str = "{}") -> dict[str, object]:
        """Invoke a named catalogue tool with JSON arguments under shared REST guards."""
        import json

        _require_mcp_api_key()
        arguments = json.loads(arguments_json) if arguments_json else {}
        if not isinstance(arguments, dict):
            raise ValueError("arguments_json must decode to an object")
        return mcp_tool_router(tool_name, arguments)

    for tool_name in MCP_TOOL_NAMES:
        if tool_name in {"get_capabilities"}:
            continue

        def _make_tool(name: str) -> Callable[[str], dict[str, object]]:
            def _tool(arguments_json: str = "{}") -> dict[str, object]:
                import json

                _require_mcp_api_key()
                arguments = json.loads(arguments_json) if arguments_json else {}
                if not isinstance(arguments, dict):
                    raise ValueError("arguments_json must decode to an object")
                return mcp_tool_router(name, arguments)

            _tool.__name__ = name
            _tool.__doc__ = f"Day 17 catalogue tool {name} with REST parity guards."
            return _tool

        server.tool()(_make_tool(tool_name))

    return server


mcp = create_mcp_server()


if __name__ == "__main__":
    mcp.run()
