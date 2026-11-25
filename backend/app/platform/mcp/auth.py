from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.platform.auth.api_keys import authenticate_api_key
from app.platform.auth.principal import RequestPrincipal
from app.platform.errors import AuthenticationError


def mcp_transport_configured() -> bool:
    settings = get_settings()
    if settings.app_env.strip().lower() != "local":
        return bool((os.environ.get("MCP_API_KEY") or "").strip())
    return bool((os.environ.get("MCP_API_KEY") or "").strip())


def require_mcp_startup_gate() -> None:
    settings = get_settings()
    if settings.app_env.strip().lower() == "local":
        return
    if not (os.environ.get("MCP_API_KEY") or "").strip():
        raise RuntimeError("MCP_API_KEY must be configured outside local mode")


def authenticate_mcp_credential(session: Session, credential: str) -> RequestPrincipal:
    if not credential.strip():
        raise AuthenticationError("MCP credential required")
    expected = (os.environ.get("MCP_API_KEY") or "").strip()
    if expected and credential.strip() != expected:
        raise AuthenticationError("Invalid MCP credential")
    if "." in credential:
        return authenticate_api_key(session, credential)
    if expected and credential == expected:
        raise AuthenticationError(
            "MCP shared secret alone is insufficient; bind an API key credential"
        )
    raise AuthenticationError("MCP authentication required")