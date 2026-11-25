"""Scope delegation rules for API keys and least-privilege checks."""

from __future__ import annotations

from app.platform.auth.rbac import ROLE_PERMISSIONS
from app.platform.errors import AuthorizationError

API_KEY_ALLOWED_SCOPES = frozenset(
    {
        "capabilities:read",
        "curriculum:read",
        "exam:read",
        "knowledge:read",
        "generation:validate",
        "jobs:read",
        "jobs:submit",
        "mcp:invoke",
    }
)


def delegatable_scopes_for_role(role: str) -> frozenset[str]:
    base = ROLE_PERMISSIONS.get(role, frozenset())
    if role in {"institution_admin", "org_admin"}:
        return base | frozenset({"api_keys:manage", "jobs:cancel"})
    return base


def delegatable_scopes_for_api_key(scopes: tuple[str, ...]) -> frozenset[str]:
    return frozenset(s for s in scopes if s in API_KEY_ALLOWED_SCOPES)


def assert_scopes_subset(requested: list[str], allowed: frozenset[str]) -> tuple[str, ...]:
    unknown = [s for s in requested if s not in API_KEY_ALLOWED_SCOPES]
    if unknown:
        raise AuthorizationError(f"Scope not delegatable via API key: {unknown[0]}")
    extras = [s for s in requested if s not in allowed]
    if extras:
        raise AuthorizationError(f"Requested scope exceeds delegation authority: {extras[0]}")
    return tuple(sorted(set(requested)))