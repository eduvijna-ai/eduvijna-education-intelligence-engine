"""D17-10 RBAC — deny by default."""

from __future__ import annotations

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "teacher": frozenset(
        {
            "capabilities:read",
            "curriculum:read",
            "exam:read",
            "knowledge:read",
            "generation:validate",
            "jobs:read",
            "mcp:invoke",
        }
    ),
    "learner": frozenset(
        {
            "capabilities:read",
            "curriculum:read",
            "exam:read",
            "knowledge:read",
        }
    ),
    "institution_admin": frozenset(
        {
            "capabilities:read",
            "curriculum:read",
            "exam:read",
            "knowledge:read",
            "generation:submit",
            "generation:validate",
            "jobs:read",
            "jobs:submit",
            "jobs:cancel",
            "api_keys:manage",
            "admin:sources",
            "mcp:invoke",
        }
    ),
    "org_admin": frozenset(
        {
            "capabilities:read",
            "curriculum:read",
            "exam:read",
            "knowledge:read",
            "generation:submit",
            "generation:validate",
            "jobs:read",
            "jobs:submit",
            "jobs:cancel",
            "api_keys:manage",
            "admin:sources",
            "mcp:invoke",
        }
    ),
}


def scopes_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(scopes: frozenset[str] | tuple[str, ...], permission: str) -> None:
    if permission not in scopes:
        from app.platform.errors import AuthorizationError

        raise AuthorizationError(f"Missing permission: {permission}")
