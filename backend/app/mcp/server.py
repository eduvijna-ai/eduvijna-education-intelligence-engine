from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from app.db.session import session_factory
from app.platform.mcp.auth import (
    authenticate_mcp_credential,
    mcp_transport_configured,
    require_mcp_startup_gate,
)
from app.platform.mcp.tools import mcp_tool_router

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


def _run_tool(name: str, credential: str, arguments_json: str) -> dict[str, object]:
    import json

    if not mcp_transport_configured():
        return {
            "blocked": True,
            "reason": "MCP transport authentication is not configured",
        }
    arguments = json.loads(arguments_json) if arguments_json else {}
    if not isinstance(arguments, dict):
        raise ValueError("arguments_json must decode to an object")
    credential_clean = credential.strip() or str(arguments.pop("mcp_credential", "")).strip()
    if not credential_clean:
        raise PermissionError("MCP credential required")
    session = session_factory()()
    try:
        principal = authenticate_mcp_credential(session, credential_clean)
        return mcp_tool_router(name, arguments, principal=principal)
    finally:
        session.close()


def create_mcp_server() -> Any:
    require_mcp_startup_gate()
    server = MCPServer("eduvijna")

    @server.tool()
    def health() -> dict[str, str]:
        """Return the MCP transport health status."""
        configured = str(mcp_transport_configured())
        return {"service": "eduvijna-mcp", "status": "ok", "auth_configured": configured}

    @server.tool()
    def get_capabilities(mcp_credential: str = "") -> dict[str, object]:
        """List server-owned capability readiness (no caller overrides)."""
        return _run_tool("get_capabilities", mcp_credential, "{}")

    @server.tool()
    def invoke_catalog_tool(
        tool_name: str,
        mcp_credential: str,
        arguments_json: str = "{}",
    ) -> dict[str, object]:
        """Invoke a named catalogue tool with JSON arguments under shared REST guards."""
        return _run_tool(tool_name, mcp_credential, arguments_json)

    for tool_name in MCP_TOOL_NAMES:
        if tool_name in {"get_capabilities"}:
            continue

        def _make_tool(name: str) -> Callable[[str, str], dict[str, object]]:
            def _tool(mcp_credential: str, arguments_json: str = "{}") -> dict[str, object]:
                return _run_tool(name, mcp_credential, arguments_json)

            _tool.__name__ = name
            _tool.__doc__ = (
                f"Day 17 catalogue tool {name}; requires mcp_credential bound to API key."
            )
            return _tool

        server.tool()(_make_tool(tool_name))

    return server


mcp = create_mcp_server()


if __name__ == "__main__":
    mcp.run()